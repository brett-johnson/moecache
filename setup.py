#!/usr/bin/env python
import os
from setuptools import setup


def localopen(fname):
    return open(os.path.join(os.path.dirname(__file__), fname))


setup(
    name='moecache',
    version='0.1',
    description='A memcached client with a different shading strategy',
    author='Zhihao Yuan',
    author_email='zhihao.yuan@rackspace.com',
    py_modules=['moecache'],
    zip_safe=True,
    license='ASL 2.0',
    keywords=['rackspace', 'memcached'],
    url='https://github.com/lichray/moecache',
    long_description=localopen('README.md').read(),
    install_requires=localopen('requirements.txt').readlines(),
    tests_require=localopen('test-requirements.txt').readlines(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 2 :: Only',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: Implementation :: PyPy',
    ]
)
