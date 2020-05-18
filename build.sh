#!/bin/bash

CHARTPRESS_OPT=""


if [ "x$TRAVIS_TAG" != "x" ]; then 
     CHARTPRESS_OPT="$CHARTPRESS_OPT --tag $TRAVIS_TAG"
fi

if [ "x$TRAVIS_COMMIT_RANGE" != "x" ]; then
    CHARTPRESS_OPT="$CHARTPRESS_OPT --commit-range $TRAVIS_COMMIT_RANGE"
fi


if [ "x$1" == "x--deploy" ]; then
    echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
    CHARTPRESS_OPT="$CHARTPRESS_OPT --push --publish-chart"
fi

git reset --hard
chartpress $CHARTPRESS_OPT
