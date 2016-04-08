#!/usr/bin/env python
import os
from setuptools import setup


def localopen(fname):
    return open(os.path.join(os.path.dirname(__file__), fname))


setup(
    name='moecache',
    version='1.0',
    description='A memcached client with a different shading strategy',
    author='Zhihao Yuan',
    author_email='lichray@gmail.com',
    py_modules=['moecache'],
    zip_safe=True,
    license='ASL 2.0',
    keywords=['rackspace', 'memcached'],
    url='https://github.com/lichray/moecache',
    long_description=localopen('README.rst').read(),
    install_requires=localopen('requirements.txt').readlines(),
    tests_require=localopen('test-requirements.txt').readlines(),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX',
        'Operating System :: MacOS :: MacOS X',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: Implementation :: PyPy',
    ]
)
