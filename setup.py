from setuptools import setup

try:
    import multiprocessing
except ImportError:
    pass

setup(
    setup_requires=['pbr>=2.0.0'],
    pbr=True,
)
