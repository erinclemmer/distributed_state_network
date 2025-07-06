#!/bin/bash

coverage run test.py && coverage report -m --omit=test.py