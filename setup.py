# Copyright (c) by it's authors. 
# Some rights reserved. See LICENSE, AUTHORS.

from setuptools import setup, find_packages
import os

setup(name='wallaby-backend-couchdb',
      version='0.1.26',
      url='https://github.com/FreshXOpenSource/wallaby-backend-couchdb',
      author='FreshX GbR',
      author_email='wallaby@freshx.de',
      packages=find_packages('.'),
      install_requires=['wallaby-backend-http']
  )
