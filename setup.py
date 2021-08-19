from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='django-ocs-observation-portal',
    description='The Observatory Control System (OCS) Observation Portal django apps',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://observatorycontrolsystem.github.io',
    author='Observatory Control System Project',
    author_email='ocs@lco.global',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Topic :: Scientific/Engineering :: Astronomy',
        'Topic :: Scientific/Engineering :: Physics'
    ],
    keywords=['observations', 'astronomy', 'astrophysics', 'cosmology', 'science', 'ocs', 'observatory'],
    packages=find_packages(),
    use_scm_version=True,
    setup_requires=['setuptools_scm', 'wheel', 'numpy>=1.16,<1.17'],
    install_requires=[
        'apscheduler>=3.7,<3.8',
        'boto3<2.0',
        'cerberus>1.0,<2.0',
        'django>=2.2,<2.3',
        'djangorestframework>=3.9,<3.10',
        'django-bootstrap4<1.2',
        'django-cors-headers>=3.0,<3.6',
        'django-dramatiq>=0.7,<0.8',
        'django-extensions>=2.1,<2.2',
        'django-filter>=2.1,<2.4',
        'django-oauth-toolkit>=1.2,<1.3',
        'django-redis-cache<2.1',
        'django-registration-redux>=2.6,<2.7',
        'django-storages>=1.7,<1.8',
        'dramatiq[redis, watch]>=1.5,<1.6',
        'drf-yasg>=1.15,<1.16',
        'elasticsearch>=5,<6',
        'gunicorn[gevent]>=19,<20',
        'lcogt-logging==0.3.2',
        'numpy>=1.16,<1.17',
        'ocs-rise-set==0.5.1',
        'psycopg2-binary>=2.8,<2.9',
        'PyPDF2>=1.26,<1.27',
        'redis==3.5.2',
        'requests>=2.22,<2.26',
        'time_intervals<2.0'
    ],
    extras_require={
        'test': ['responses==0.10.6', 'mixer==6.1.3', 'Faker==0.9.1']
    },
    include_package_data=True,
)
