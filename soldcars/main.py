import argparse
import asyncio
import json
import logging
import socket

from functools import wraps

import aiohttp

from aiohttp import web
from object_validator import ValidationError, validate
from object_validator import DictScheme

from .db import Car, Motor, ReplicaSet
from .exceptions import BaseError

routes = web.RouteTableDef()

log = logging.getLogger()


def jsonerror(exc, reason=None, text=None):
    """Instantiate specified error as JSON mediatype."""

    assert isinstance(exc, web.HTTPException)

    info = {
        "reason": reason or exc.reason,
        "error": text or exc.text,
    }

    cls = exc.__class__

    return cls(text=json.dumps(info), content_type="application/json")


def jsonhandler(coro):
    """JSON request wrapper."""

    @wraps(coro)
    async def wrapper(*args, **kwargs):
        try:
            response = await coro(*args, **kwargs)
            return web.json_response(response)
        except BaseError as e:
            raise jsonerror(web.HTTPBadRequest(text=str(e)))
        except web.HTTPException as e:
            raise jsonerror(e)
        except Exception as e:
            log.error("Internal server error: %s", e, exc_info=True)
            raise jsonerror(web.HTTPInternalServerError())
    return wrapper


def jsonvalidate(scheme=None):
    def outer_wrapper(coro):
        @wraps(coro)
        async def inner_wrapper(request, *args, **kwargs):
            try:
                data = await request.json()
            except (ValueError, TypeError):
                raise web.HTTPBadRequest(text="Could not decode JSON object.")

            if scheme:
                try:
                    data = validate("request", data, DictScheme(scheme))
                except ValidationError as e:
                    raise web.HTTPBadRequest(text=e.get_message())
            return await coro(request, data, *args, **kwargs)
        return inner_wrapper
    return outer_wrapper


@routes.get("/api/cars/{serial}")
@jsonhandler
async def get_car(request):
    try:
        serial = int(request.match_info["serial"])
    except ValueError:
        raise web.HTTPBadRequest(text="Parameter 'serial' has invalid type.")

    # NOTE: using read from secondary with possible
    #       stale data for increase read capacity
    car = await Car.one(serial, stale_ok=True)
    return car.asdict()


@routes.post("/api/cars")
@jsonhandler
@jsonvalidate(Car.get_scheme())
async def add_car(request, data):
    car = Car(data)
    await car.insert()
    return {"serial": car["serialNumber"]}


@routes.get("/api/hostname")
@jsonhandler
async def get_cars(request):
    return {"host": socket.gethostname()}


async def init(loop):
    app = web.Application(loop=loop)
    app.add_routes(routes)

    Motor().default(io_loop=loop)
    return app


def main():
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(init(loop))
    web.run_app(app, port=3000)


def cli():
    logging.basicConfig(level=logging.FATAL)

    parser = argparse.ArgumentParser("soldcars-cli")
    commands = parser.add_subparsers(dest="command")

    fakecars = commands.add_parser("fake")
    fakecars.add_argument("count", type=int, help="cars count")
    fakecars.add_argument("start", type=int, help="serial number start value")

    fakesend = commands.add_parser("fakesend")
    fakesend.add_argument("serial", type=int, help="car serial")
    fakesend.add_argument("--host", default="balancer", help="app host[:port]")

    listcars = commands.add_parser("list")
    listcars.add_argument("--limit", type=int, help="limit cars list")

    dropcars = commands.add_parser("drop")
    assert dropcars

    indexcars = commands.add_parser("index")
    assert indexcars

    replcars = commands.add_parser("replica")
    assert replcars

    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    Motor().default(io_loop=loop)

    if args.command == "fake":
        for i in range(args.start, args.start + args.count):
            car = Car.get_mocked({"serialNumber": i, "modelYear": i})
            loop.run_until_complete(car.insert())
    elif args.command == "fakesend":
        async def send(host, serial):
            car = Car.get_mocked({"serialNumber": serial})
            url = f"http://{host}/api/cars"
            session = aiohttp.ClientSession()
            async with session.post(url, data=car.asjson()) as response:
                print(await response.json())
            await session.close()
        loop.run_until_complete(send(args.host, args.serial))
    elif args.command == "list":
        cursor = Car.collection().find()
        for car in loop.run_until_complete(cursor.to_list(args.limit or 10)):
            print(car)
    elif args.command == "drop":
        loop.run_until_complete(Car.collection().drop())
    elif args.command == "index":
        loop.run_until_complete(Car.ensure_index())
    elif args.command == "replica":
        async def replica():
            replset = ReplicaSet(loop=loop)
            await replset.init()
            await replset.wait()
        loop.run_until_complete(replica())
    else:
        parser.error("too few arguments")

    Motor().close()
    loop.close()
