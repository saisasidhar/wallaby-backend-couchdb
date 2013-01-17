# Copyright (c) by it's authors. 
# Some rights reserved. See LICENSE, AUTHORS.

from setuptools import setup, find_packages
import os

setup(name='wallaby-backend-couchdb',
      version='0.1.29',
      url='https://github.com/FreshXOpenSource/wallaby-backend-couchdb',
      author='FreshX GbR',
      author_email='wallaby@freshx.de',
      license='BSD',
      description='Wallaby backend for CouchDB.',
      package_data={'': ['LICENSE', 'AUTHORS', 'README.md']},
      classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: Twisted',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: BSD License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries'
      ],
      packages=find_packages('.'),
      install_requires=['wallaby-backend-http']
  )
