import argparse
import sys
import time
import logging
import homematicip
import prometheus_client
from homematicip.home import Home
from homematicip.device import WallMountedThermostatPro, TemperatureHumiditySensorWithoutDisplay,\
     TemperatureHumiditySensorOutdoor, TemperatureHumiditySensorDisplay

logging.basicConfig(level=logging.INFO, format='%(asctime)-15s %(message)s', datefmt="%Y-%m-%d %H:%M:%S")


class Exporter(object):
    # the HomematicIP client
    home_client = None

    def __init__(self, args):
        self.__metric_port = args.metric_port
        self.__collect_interval_seconds = args.collect_interval_seconds

        logging.info(
            "using config file '{}' and exposing metrics on port '{}'".format(args.config_file, self.__metric_port)
        )

        self.__init_client(args.config_file, args.auth_token, args.access_point)
        self.__init_metrics()
        self.__collect_homematicip_info()
        try:
            prometheus_client.start_http_server(int(self.__metric_port))
        except Exception as e:
            logging.fatal(
                "starting the http server on port '{}' failed with: {}".format(self.__metric_port, str(e))
            )
            sys.exit(1)

    def __init_client(self, config_file, auth_token, access_point):
        if auth_token and access_point:
            config = homematicip.HmipConfig(
                auth_token=auth_token,
                access_point= access_point,
                log_level=30,
                log_file='hmip.log',
                raw_config=None,
            )
        else:
            config = homematicip.load_config_file(config_file=config_file)

        try:
            self.home_client = Home()
            self.home_client.set_auth_token(config.auth_token)
            self.home_client.init(config.access_point)
        except Exception as e:
            logging.fatal(
                "Initializing HomematicIP client failed with: {}".format(str(e))
            )
            sys.exit(1)

    def __init_metrics(self):
        namespace = 'homematicip'
        labelnames = ['room', 'device_label']
        detail_labelnames = ['device_type', 'firmware_version', 'last_status_update', 'permanently_reachable']

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

    def __collect_homematicip_info(self):
        try:
            self.version_info.labels(
                api_version=self.home_client.currentAPVersion
            ).set(1)
            logging.info(
                "current homematic ip api version: '{}'".format(self.home_client.currentAPVersion)
            )
        except Exception as e:
            logging.warning(
                "collecting version info failed with: {}".format(str(e))
            )

    def __collect_thermostat_metrics(self, room, device):
        self.metric_temperature_actual.labels(room=room, device_label=device.label).set(device.actualTemperature)
        self.metric_temperature_setpoint.labels(room=room, device_label=device.label).set(device.setPointTemperature)
        self.metric_humidity_actual.labels(room=room, device_label=device.label).set(device.humidity)
        logging.info(
            "room: {}, label: {}, temperature_actual: {}, temperature_setpoint: {}, humidity_actual: {}"
            .format(room, device.label, device.actualTemperature, device.setPointTemperature, device.humidity)
        )

    def __collect_device_metrics(self,room, device):
        self.metric_device_info.labels(
            room=room,
            device_label=device.label,
            device_type=device.deviceType.lower(),
            firmware_version=device.firmwareVersion,
            permanently_reachable=device.permanentlyReachable
        ).set(1)
        self.metric_last_status_update.labels(
            room=room,
            device_label=device.label
        ).set(device.lastStatusUpdate.timestamp(),)
        logging.info(
            "found device: room: {}, label: {}, device_type: {}, firmware_version: {}, last_status_update: {}, permanently_reachable: {}"
            .format(room, device.label, device.deviceType.lower(), device.firmwareVersion, device.lastStatusUpdate, device.permanentlyReachable)
        )

    def collect(self):
        try:
            self.home_client.get_current_state()
            for g in self.home_client.groups:
                if g.groupType == "META":
                    for d in g.devices:
                        # collect general device metrics
                        self.__collect_device_metrics(g.label, d)
                        # collect temperature, humidity
                        if isinstance(d, (WallMountedThermostatPro, TemperatureHumiditySensorDisplay,
                                          TemperatureHumiditySensorWithoutDisplay, TemperatureHumiditySensorOutdoor)):
                            self.__collect_thermostat_metrics(g.label, d)

        except Exception as e:
            logging.warning(
                "collecting status from device(s) failed with: {}".format(str(e))
            )
        finally:
            logging.info('waiting {}s before next collection cycle'.format(self.__collect_interval_seconds))
            time.sleep(self.__collect_interval_seconds)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HomematicIP Prometheus Exporter')
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

    # Start up the server to expose the metrics.
    e = Exporter(parser.parse_args())
    # Generate some requests.
    while True:
        e.collect()
