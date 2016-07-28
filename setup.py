from setuptools import setup, find_packages

install_requires = [
    'needle',
    'paste'
]

setup(name='stitching',
      version=0.1,
      description='Isolated visual testing',
      classifiers=[
          "Programming Language :: Python",
      ],
      author='bruk habtu',
      author_email='bruk@beanfield.com ',
      url='',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires=install_requires, )
