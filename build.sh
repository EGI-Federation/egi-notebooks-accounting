#!/bin/bash

CHARTPRESS_OPT=""

if [ "x$TRAVIS_TAG" != "x" ]; then 
     CHARTPRESS_OPT="$CHARTPRESS_OPT --tag $TRAVIS_TAG"
fi

if [ "x$DOCKER_PASSWORD" != "x" ]; then
    echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
    CHARTPRESS_OPT="$CHARTPRESS_OPT --push --publish-chart"
fi

chartpress $CHARTPRESS_OPT
