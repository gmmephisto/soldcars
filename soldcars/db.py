"""
{
    "ownerName": "string",
    "serialNumber": "uint64",
    "modelYear": "uint64",
    "code": "string",
    "vehicleCode": "string",
    "engine": {
        "capacity": "uint16",
        "numCylinders": "uint8",
        "maxRpm": "uint16",
        "manufacturerCode": "char",
    },
    "fuelFigures": {
        "speed": "uint16",
        "mpg": "float",
        "usageDescription": "string",
    },
    "performanceFigures": {
        "octaneRating": "uint16",
        "acceleration": {
            "mph": "uint16",
            "seconds": "float",
        },
    },
    "manufacturer": "string",
    "model": "string",
    "activationCode": "string",
}
"""

import copy
import json
import os
import random
import string
import asyncio

from collections.abc import MutableMapping
from functools import partial

import motor.motor_asyncio as aiomotor
import pymongo
import pymongo.errors

from pymongo import ReadPreference, WriteConcern
from object_validator import validate
from object_validator import String, Integer, Float, DictScheme

from .exceptions import CarNotFound, CarAlreadyExists
from .utils import Singleton


MIN_STRING_LEN = 3
"""Minimum string field length."""

MAX_STRING_LEN = 255
"""Maximum string field length."""

OrdinaryString = partial(String,
                         min_length=MIN_STRING_LEN,
                         max_length=MAX_STRING_LEN)
"""Orinary string field."""

Char = partial(String, min_length=0, max_length=1)
"""Char fields."""

Integer8 = partial(Integer, min=0, max=(2 ** 8) - 1)
Integer16 = partial(Integer, min=0, max=(2 ** 16) - 1)
Integer32 = partial(Integer, min=0, max=(2 ** 32) - 1)
# FIXME: try to store long integers as strings in database
#        and convert them in ORM classes
# Integer64 = partial(Integer, min=0, max=(2 ** 64) - 1)
"""Integer fields."""


class Motor(metaclass=Singleton):
    __slots__ = ("_clients",)

    def __init__(self):
        self._clients = {}

    def kwargs(self, **kwargs):
        """Return motor arguments."""

        client_kwargs = {
            "host": os.getenv("MONGODB_HOSTS", "mongo:27017").split(","),
            "replicaSet": os.getenv("MONGODB_REPLSET")
        }
        return client_kwargs

    def new(self, key, **kwargs):
        """Return and register new motor with specified key."""

        client = self._clients.pop(key, None)
        if client:
            client.close()

        client_kwargs = self.kwargs(**kwargs)
        self._clients[key] = client = \
            aiomotor.AsyncIOMotorClient(**client_kwargs)
        return client

    def get(self, key):
        """Return motor by key."""

        return self._clients[key]

    def default(self, **kwargs):
        """Return default motor."""

        key = "default"
        try:
            return self.get(key)
        except KeyError:
            return self.new(key, **kwargs)

    def close(self):
        """Close motors."""

        for motor in self._clients.values():
            motor.close()


class Car(MutableMapping):
    __slots__ = ("_object",)
    __scheme__ = {
        "ownerName": OrdinaryString(),
        "serialNumber": Integer32(),
        "modelYear": Integer32(),
        # "serialNumber": Integer64(),
        # "modelYear": Integer64(),
        "code": OrdinaryString(),
        "vehicleCode": OrdinaryString(),
        "engine": DictScheme({
            "capacity": Integer16(),
            "numCylinders": Integer8(),
            "maxRpm": Integer16(),
            "manufacturerCode": Char(),
        }),
        "fuelFigures": DictScheme({
            "speed": Integer16(),
            "mpg": Float(),
            "usageDescription": OrdinaryString(),
        }),
        "performanceFigures": DictScheme({
            "octaneRating": Integer16(),
            "acceleration": DictScheme({
                "mph": Integer16(),
                "seconds": Float(),
            }),
        }),
        "manufacturer": OrdinaryString(),
        "model": OrdinaryString(),
        "activationCode": OrdinaryString(),
    }

    __database__ = "soldcars"
    __collection__ = "cars"
    __write_majority__ = WriteConcern(w="majority", wtimeout=5000)

    @classmethod
    def get_scheme(cls):
        """Return Car scheme."""

        return cls.__scheme__

    @classmethod
    def validate(cls, data):
        """Validate Car document and return the instance."""

        return cls(validate("Car", data, DictScheme(cls.__scheme__)))

    @classmethod
    def database(cls):
        """Return database instance."""

        return Motor().default()[cls.__database__]

    @classmethod
    def collection(cls, stale_ok=False, majority=False):
        """Return collection instance."""

        kwargs = {}
        if stale_ok:
            kwargs["read_preference"] = ReadPreference.SECONDARY_PREFERRED
        elif majority:
            kwargs["write_concern"] = cls.__write_majority__

        return aiomotor.AsyncIOMotorCollection(
            cls.database(), cls.__collection__, **kwargs)

    @classmethod
    async def ensure_index(cls):
        """Ensure collection index."""

        await cls.collection().create_index([
            ("serialNumber", pymongo.ASCENDING)
        ], unique=True)

    @classmethod
    async def one(cls, serial, add_query=None, fields=None,
                  required=True, stale_ok=False):
        """Return a one Car document."""

        query = {
            "serialNumber": serial
        }
        if add_query:
            query.update(add_query)

        car = await cls.collection(
            stale_ok=stale_ok).find_one(query, projection=fields)

        if not car and required:
            raise CarNotFound(serial)

        if car:
            car.pop("_id")
        return cls(car)

    @classmethod
    def get_mocked(cls, override=None):
        """Mock a one Car document.

        Attention: use only in tests and cli tools to fake documents!
        """

        def randstr(length):
            letters = string.ascii_lowercase
            return ''.join(random.choice(letters) for i in range(length))

        def _mock(part):
            d = {}
            for key, value in part.items():
                # NOTE: using mangled attributes is not a good way
                #       but object_validator library was not intend to
                #       convert or generate new data by the scheme.
                if isinstance(value, DictScheme):
                    d[key] = _mock(value._DictScheme__scheme)
                elif isinstance(value, Integer):
                    d[key] = random.randint(value._BasicNumber__min or 0,
                                            value._BasicNumber__max or 100)
                elif isinstance(value, Float):
                    d[key] = random.uniform(value._BasicNumber__min or 0,
                                            value._BasicNumber__max or 100)
                    d[key] = round(d[key], 2)
                elif isinstance(value, String):
                    d[key] = randstr(
                        random.randint(value._String__min_length,
                                       value._String__max_length))
            return d

        mocked = _mock(cls.get_scheme())
        mocked.update(override or {})
        return cls(mocked)

    def __init__(self, data):
        self._object = data or {}

    def __getitem__(self, key):
        return self._object[key]

    def __setitem__(self, key, value):
        self._object[key] = value

    def __delitem__(self, key):
        self._object.pop(key)

    def __iter__(self):
        return iter(self._object)

    def __len__(self):
        return len(self._object)

    def asdict(self):
        """Return Car document as dictionary."""

        return copy.deepcopy(self._object)

    def asjson(self):
        """Return Car document as JSON."""

        return json.dumps(self._object)

    async def insert(self, majority=True):
        """Insert Car document in collection."""

        try:
            document_id = self["_id"] = \
                await self.collection(majority=majority).insert_one(self)
        except pymongo.errors.WTimeoutError:
            # FIXME: add retry on write timeout
            raise
        except pymongo.errors.DuplicateKeyError:
            raise CarAlreadyExists(self["serialNumber"])

        return document_id


class ReplicaSet:
    def __init__(self, name=None, hosts=None, loop=None):
        name = os.getenv("MONGODB_REPLSET", name)
        if not name:
            raise Exception("Invalid replica set name.")
        self.name = name
        hosts = os.getenv("MONGODB_HOSTS").split(",") or hosts
        if not hosts:
            raise Exception("Invalid replica set hists.")
        self.hosts = sorted(hosts)
        self.admin = self.hosts[0]
        self.loop = loop or asyncio.get_event_loop()
        self.client = aiomotor.AsyncIOMotorClient(host=[self.admin])
        self.timeout = 300 * len(self.hosts)

    async def init(self):
        replset = await self.client.local.system.replset.find_one()
        if replset:
            return replset

        config = {
            "_id": self.name,
            "members": [{
                "_id": i,
                "host": host,
            } for i, host in enumerate(self.hosts)]
        }
        return await self.client.admin.command("replSetInitiate", config)

    async def wait(self):
        start = self.loop.time()
        while self.loop.time() - start < self.timeout:
            try:
                status = await self.client.admin.command("replSetGetStatus")
                alive = True
                for member in status["members"]:
                    alive &= member["state"] in (1, 2)  # PRIMARY, SECONDARY
            except pymongo.errors.OperationFailure:
                status = None
                alive = False
            if alive:
                break
            asyncio.sleep(1)
        else:
            if status is None:
                raise Exception("Unable to retrieve replica set status.")
            else:
                raise Exception(
                    f"Unable to intialize to replica set {self.name}.")
        return self.loop.time() - start
