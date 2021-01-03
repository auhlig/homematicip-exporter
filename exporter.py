import argparse
import sys
import time
import logging
import homematicip
import prometheus_client
from homematicip.home import Home, EventType
from homematicip.device import WallMountedThermostatPro, TemperatureHumiditySensorWithoutDisplay, \
    TemperatureHumiditySensorOutdoor, TemperatureHumiditySensorDisplay, ShutterContact, HeatingThermostat, \
    Switch, SwitchMeasuring

logging.basicConfig(level=logging.INFO, format='%(asctime)-15s %(message)s', datefmt="%Y-%m-%d %H:%M:%S")


class Exporter(object):
    """
    Prometheus Exporter for Homematic IP devices
    """
    def __init__(self, args):
        """
        initializes the exporter

        :param args: the argparse.Args
        """
        
        self.__home_client = None
        self.__metric_port = int(args.metric_port)
        self.__collect_interval_seconds = args.collect_interval_seconds
        self.__log_level = int(args.log_level)

        logging.info(
            "using config file '{}' and exposing metrics on port '{}'".format(args.config_file, self.__metric_port)
        )

        self.__init_client(args.config_file, args.auth_token, args.access_point, args.enable_event_metrics)
        self.__init_metrics()
        self.__collect_homematicip_info()
        try:
            prometheus_client.start_http_server(self.__metric_port)
        except Exception as e:
            logging.fatal(
                "starting the http server on port '{}' failed with: {}".format(self.__metric_port, str(e))
            )
            sys.exit(1)

    def __init_client(self, config_file, auth_token, access_point, enable_event_metrics):
        if auth_token and access_point:
            config = homematicip.HmipConfig(
                auth_token=auth_token,
                access_point= access_point,
                log_level=self.__log_level,
                log_file='hmip.log',
                raw_config=None,
            )
        else:
            config = homematicip.load_config_file(config_file=config_file)

        try:
            self.__home_client = Home()
            self.__home_client.set_auth_token(config.auth_token)
            self.__home_client.init(config.access_point)
            # metrics on events
            if enable_event_metrics:
                self.__home_client.onEvent += self.__collect_event_metrics
                self.__home_client.enable_events()
        except Exception as e:
            logging.fatal(
                "Initializing HomematicIP client failed with: {}".format(str(e))
            )
            sys.exit(1)

    def __init_metrics(self):
        namespace = 'homematicip'
        labelnames = ['room', 'device_label']
        detail_labelnames = ['device_type', 'firmware_version', 'permanently_reachable']
        event_device_labelnames = ['device_label']
        event_group_labelnames = ['group_label']
        event_labelnames = ['type', 'window_state', 'sabotage']

        self.version_info = prometheus_client.Gauge(
            name='version_info',
            documentation='HomematicIP info',
            labelnames=['api_version'],
            namespace=namespace
        )
        self.metric_temperature_actual = prometheus_client.Gauge(
            name='temperature_actual',
            documentation='Actual temperature',
            labelnames=labelnames,
            namespace=namespace
        )
        self.metric_temperature_setpoint = prometheus_client.Gauge(
            name='temperature_setpoint',
            documentation='Set point temperature',
            labelnames=labelnames,
            namespace=namespace
        )
        self.metric_valve_adaption_needed = prometheus_client.Gauge(
            name='valve_adaption_needed',
            documentation='must the adaption re-run?',
            labelnames=labelnames,
            namespace=namespace
        )
        self.metric_temperature_offset = prometheus_client.Gauge(
            name='temperature_offset',
            documentation='the offset temperature for the thermostat',
            labelnames=labelnames,
            namespace=namespace
        )
        self.metric_valve_position = prometheus_client.Gauge(
            name='valve_position',
            documentation='the current position of the valve 0.0 = closed, 1.0 max opened',
            labelnames=labelnames,
            namespace=namespace
        )
        self.metric_humidity_actual = prometheus_client.Gauge(
            name='humidity_actual',
            documentation='Actual Humidity',
            labelnames=labelnames,
            namespace=namespace
        )
        self.metric_last_status_update = prometheus_client.Gauge(
            name='last_status_update',
            documentation="Device last status update",
            labelnames=labelnames,
            namespace=namespace
        )
        self.metric_device_info = prometheus_client.Gauge(
            name='device_info',
            documentation='Device information',
            labelnames=labelnames+detail_labelnames,
            namespace=namespace
        )
        self.metric_power_consumption = prometheus_client.Gauge(
            name='power_consumption',
            documentation='Power consumption',
            labelnames=labelnames,
            namespace=namespace
        )
        self.metric_energy_counter = prometheus_client.Gauge(
            name='energy_counter',
            documentation='Energy Counter',
            labelnames=labelnames,
            namespace=namespace
        )
        self.metric_switch_on = prometheus_client.Gauge(
            name='switch',
            documentation='Switch turned on',
            labelnames=labelnames,
            namespace=namespace
        )                
        self.metric_device_event = prometheus_client.Counter(
            name='device_event',
            documentation='events triggered by a device',
            labelnames=event_device_labelnames+event_labelnames,
            namespace=namespace
        )
        self.metric_group_event = prometheus_client.Counter(
            name='group_event',
            documentation='events triggered by a group',
            labelnames=event_group_labelnames+event_labelnames,
            namespace=namespace,
        )

    def __collect_homematicip_info(self):
        try:
            self.version_info.labels(
                api_version=self.__home_client.currentAPVersion
            ).set(1)
            logging.debug(
                "current homematic ip api version: '{}'".format(self.__home_client.currentAPVersion)
            )
        except Exception as e:
            logging.warning(
                "collecting version info failed with: {}".format(str(e))
            )

    def __collect_thermostat_metrics(self, room, device):
        if device.actualTemperature:
            self.metric_temperature_actual.labels(room=room, device_label=device.label).set(device.actualTemperature)

        if device.setPointTemperature:
            self.metric_temperature_setpoint.labels(room=room, device_label=device.label).set(device.setPointTemperature)

        if device.humidity:
            self.metric_humidity_actual.labels(room=room, device_label=device.label).set(device.humidity)
        logging.info(
            "room: {}, label: {}, temperature_actual: {}, temperature_setpoint: {}, humidity_actual: {}"
            .format(room, device.label, device.actualTemperature, device.setPointTemperature, device.humidity)
        )

    def __collect_heating_metrics(self, room, device):

        # Do not check with if as 0 equals false
        self.metric_temperature_actual.labels(room=room, device_label=device.label).set(device.valveActualTemperature)
        self.metric_temperature_setpoint.labels(room=room, device_label=device.label).set(device.setPointTemperature)
        self.metric_valve_adaption_needed.labels(room=room, device_label=device.label).set(device.automaticValveAdaptionNeeded)
        self.metric_temperature_offset.labels(room=room, device_label=device.label).set(device.temperatureOffset)
        self.metric_valve_position.labels(room=room, device_label=device.label).set(device.valvePosition)

        logging.info(
            "room: {}, label: {}, temperature_actual: {}, temperature_setpoint: {}, valve_adaption_needed: {}, "
            "temperature_offset {}, valve_position: {}"
                .format(room, device.label, device.valveActualTemperature, device.setPointTemperature,
                        device.automaticValveAdaptionNeeded, device.temperatureOffset, device.valvePosition)
        )

    def __collect_device_info_metrics(self,room, device):
        logging.info(
            "found device: room: {}, label: {}, device_type: {}, firmware_version: {}, last_status_update: {}, permanently_reachable: {}"
                .format(room, device.label, device.deviceType.lower(), device.firmwareVersion, device.lastStatusUpdate,
                        device.permanentlyReachable)
        )
        # general device info metric
        self.metric_device_info.labels(
            room=room,
            device_label=device.label,
            device_type=device.deviceType.lower(),
            firmware_version=device.firmwareVersion,
            permanently_reachable=device.permanentlyReachable
        ).set(1)
        if device.lastStatusUpdate:
            # last status update metric
            self.metric_last_status_update.labels(
                room=room,
                device_label=device.label
            ).set(device.lastStatusUpdate.timestamp())

    def __collect_switch_metrics(self, room, device):
        self.metric_switch_on.labels(room=room,device_label=device.label).set(device.on)

    def __collect_power_metrics(self, room, device):
        logging.info(
            "found device: room: {}, label: {}, device_type: {}, firmware_version: {}, last_status_update: {}, permanently_reachable: {}"
                .format(room, device.label, device.deviceType.lower(), device.firmwareVersion, device.lastStatusUpdate,
                        device.permanentlyReachable)
        )
        # general device info metric
        logging.info(device.currentPowerConsumption)
        self.metric_power_consumption.labels(room=room,device_label=device.label).set(device.currentPowerConsumption),
        self.metric_energy_counter.labels(room=room,device_label=device.label).set(device.energyCounter)

    def __collect_event_metrics(self, eventList):
        for event in eventList:
            type = event["eventType"]
            data = event["data"]

            if type is EventType.DEVICE_CHANGED:
                _window_state = _sabotage = None
                if isinstance(data, ShutterContact):
                    _window_state = str(data.windowState).lower()
                    _sabotage = str(data.sabotage).lower()
                    self.metric_device_event.labels(
                        device_label=data.label,
                        type=str(type).lower(),
                        window_state=_window_state,
                        sabotage=_sabotage
                    ).inc()
                    logging.info(
                        "got device event type: {}, label: {}, window_state: {}, sabotage: {}"
                            .format(type, data.label, _window_state, _sabotage)
                    )

    def collect(self):
        """
        collect discovers all devices and generates metrics
        """
        try:
            self.__home_client.get_current_state()
            for g in self.__home_client.groups:
                if g.groupType == "META":
                    for d in g.devices:
                        # collect general device metrics
                        self.__collect_device_info_metrics(g.label, d)
                        # collect temperature, humidity
                        if isinstance(d, (WallMountedThermostatPro, TemperatureHumiditySensorDisplay,
                                          TemperatureHumiditySensorWithoutDisplay, TemperatureHumiditySensorOutdoor)):
                            self.__collect_thermostat_metrics(g.label, d)
                        elif isinstance(d, HeatingThermostat):
                            logging.info("Device of type heating")
                            self.__collect_heating_metrics(g.label, d)
                        elif isinstance(d, SwitchMeasuring):
                            logging.info("Device of type switch measuring")
                            self.__collect_power_metrics(g.label, d)
                            self.__collect_switch_metrics(g.label, d)                            
                        elif isinstance(d, Switch):
                            logging.info("Device of type switch measuring")
                            self.__collect_switch_metrics(g.label, d)

        except Exception as e:
            logging.warning(
                "collecting status from device(s) failed with: {1}".format(str(e))
            )
        finally:
            logging.info('waiting {}s before next collection cycle'.format(self.__collect_interval_seconds))
            time.sleep(self.__collect_interval_seconds)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='HomematicIP Prometheus Exporter',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--metric-port',
                        default=8000,
                        help='port to expose the metrics on')
    parser.add_argument('--config-file',
                        default='/etc/homematicip-rest-api/config.ini',
                        help='path to the configuration file')
    parser.add_argument('--collect-interval-seconds',
                        default=30,
                        help='collection interval in seconds')
    parser.add_argument('--auth-token',
                        default=None,
                        help='homematic IP auth token')
    parser.add_argument('--access-point',
                        default=None,
                        help='homematic IP access point id')
    parser.add_argument('--enable-event-metrics',
                        default=False,
                        help='collect event metrics')
    parser.add_argument('--log-level',
                        default=30,
                        help='log level')

    # Start up the server to expose the metrics.
    e = Exporter(parser.parse_args())
    # Generate some requests.
    while True:
        e.collect()
