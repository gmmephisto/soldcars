# Soldcars: application for store sold cars

## Install

* Up containers:
    * `docker-compose up -d --scale app=3`
* Ensure database index:
    * `docker-compose exec cli soldcars-cli index`

## Usage

* From `cli` container:
    * `docker-compose exec cli`
    * `(cli) # apk add curl`
    * `(cli) # curl balancer/api/cars/<serial>`
* From `localhost`:
    * `curl localhost/api/cars/<serial>`
    * `curl localhost/api/hostname` - detect backend hostname
