from setuptools import setup, find_packages
import subprocess

setup(
        name='slobot',
        version=subprocess.getoutput('git describe --tags'),
        description="SwissLinux.Org's IRC Bot",
        author='Maxime Augier',
        author_email='max@xolus.net',
        packages=['slobot'],
        license='GPL2',
        install_requires=['irc','pyyaml','sleekxmpp'],
        entry_points={
                'console_scripts': ['slobot = slobot:main']
        }
)
