#!/usr/bin/env python
import os
from setuptools import setup


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name='moecache',
    version='0.1',
    description='A memcache client with a different shading strategy',
    author='Zhihao Yuan',
    author_email='zhihao.yuan@rackspace.com',
    py_modules=['moecache'],
    zip_safe=True,
    license='ASL 2.0',
    keywords=['rackspace', 'memcache'],
    url='https://github.com/lichray/moecache',
    long_description=read('README.md'),
    install_requires=open('requirements.txt').readlines(),
    tests_require=open('test-requirements.txt').readlines()
)
