# Soldcars: application for store sold cars

## Arch & Tech

* Application backend: `asyncio`, `aiohttp`, `motor`
* Database: `mongodb`
* Balancer: `traefik`
* Deploy: `docker`, `docker-compose`

Application backend is stateless, lives on port 3000 and could be scaled up to several instances. Balancer lives on port 80 and works as reverse-proxy to application instances. Also, it listens to docker events and detects application instances scaling.
Database deployed in three containers as a replica set. The application uses that setup for increasing read capacity and data durability.

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

## Pitfails

* `aiohttp` has weird web handlers atomicity. On graceful shutdown, it cancels newest and already running handlers. It could be fixed by using `aiojobs` library for spawning tasks and protect web handlers, but it doesn't work as described in the documentation and doesn't fix the problem.
