from setuptools import setup, find_packages

setup(
    name='schwab',
    version='0.1.0',
    description='Schwab http api',
    packages=find_packages(exclude=['ez_setup', 'tests', 'tests.*']),
    zip_safe=False,
    install_requires=[
        'requests',
        'beautifulsoup4',
        'python-dateutil<2',
    ],
    classifiers=[
        "Development Status :: 3 - Alpha"
    ],
    entry_points= {
        'console_scripts': [
            'schwab = schwab:main',
        ],
    }
)
