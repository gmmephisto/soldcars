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

from collections.abc import MutableMapping
from functools import partial

import motor.motor_asyncio as aiomotor
import pymongo

from pymongo import ReadPreference
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
Integer64 = partial(Integer, min=0, max=(2 ** 64) - 1)
"""Integer fields."""


def get_client(**kwargs):
    """Return MongoDB client object."""

    client_kwargs = {
        "host": os.getenv("MONGODB_HOSTS", "mongo:27017").split(","),
        "replicaSet": os.getenv("MONGODB_REPLSET")
    }
    client_kwargs.update(kwargs)

    return aiomotor.AsyncIOMotorClient(**client_kwargs)


class Motor(metaclass=Singleton):
    __slots__ = ("_clients",)

    def __init__(self):
        self._clients = {}

    def new(self, key, **kwargs):
        """Return and register new motor with specified key."""

        client = self._clients.pop(key, None)
        if client:
            client.close()

        client_kwargs = {
            "host": os.getenv("MONGODB_HOSTS", "mongo:27017").split(","),
            "replicaSet": os.getenv("MONGODB_REPLSET")
        }
        client_kwargs.update(kwargs)
        self._clients[key] = \
            client = aiomotor.AsyncIOMotorClient(**client_kwargs)
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


class Car(MutableMapping):
    __slots__ = ("_object",)
    __scheme__ = {
        "ownerName": OrdinaryString(),
        "serialNumber": Integer64(),
        "modelYear": Integer64(),
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
    def collection(cls, stale_ok=False):
        """Return collection instance."""

        kwargs = {}
        if stale_ok:
            kwargs["read_preference"] = ReadPreference.SECONDARY_PREFERRED

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

    async def insert(self):
        """Insert Car document in collection."""

        try:
            document_id = self["_id"] = \
                await self.collection().insert_one(self)
        except pymongo.errors.DuplicateKeyError:
            raise CarAlreadyExists(self["serialNumber"])

        return document_id
