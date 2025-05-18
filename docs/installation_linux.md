# Road core installation on Linux

## Prerequisities

- git
- Python 3.11 or 3.12
- pip

## Installation steps

1. `pip install --user pdm`
1. `pdm --version` -- should return no error
1. Clone the repo to the current dir:
`git clone https://github.com/road-core/service`
1. `cd service`
1. `pdm info` -- should return no error
1. `pdm install`
