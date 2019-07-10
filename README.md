# Soldcars: application for store sold cars

## Install

* Install `docker` and `docker-compose`:
    * https://docs.docker.com/install/
    * https://docs.docker.com/compose/install/
* Build images:
    * `docker-compose build`
* Up containers:
    * `docker-compose up -d --scale app=3`
* Init database replica and ensure database index:
    * `docker-compose exec cli soldcars-cli replica`
    * `docker-compose exec cli soldcars-cli index`
* Add fake cars (optional):
    * `docker-compose exec cli soldcars-cli fake 1000 0`

## Usage

* From `cli` container:
    * `docker-compose exec cli`
    * `(cli) # apk add curl`
    * `(cli) # curl balancer/api/cars/<serial>`
* From `localhost`:
    * `curl localhost/api/cars/<serial>`
    * `curl localhost/api/hostname` - detect backend hostname

## Manage

Use `cli` container and `soldcars-cli` tool for manage database, add fake cars, etc.

* List all cars in database:
    * `docker-compose exec cli soldcars-cli list`
    * `docker-compose exec cli soldcars-cli list --limit 50`
* Drop all cars in database:
    * `docker-compose exec cli soldcars-cli drop`
* Add fake cars (1000 cars, serial number start with 0):
    * `docker-compose exec cli soldcars-cli 1000 0`
* Send fake car object to app API:
    * `docker-compose exec cli soldcars-cli fakesend <serial>`
    * `docker-compose exec cli soldcars-cli fakesend <serial> --host <host>[:<port>]`
