# EGI Notebooks Accounting

EGI Notebooks accounting tools.

## Required settings

See *notebooks-accounting/values.yaml* for Helm package values.

Enable APEL accounting:

    ssm:
      # enable APEL sender
      schedule: 42 1 * * *
      hostcert: ...
      hostkey: ...

Enable EOSC accounting:

    eosc:
      schedule: 42 1 * * *
      tokenUrl:
      clientId:
      clientSecret:
      accountingUrl:
      installationId:
      flavorMetrics:
        flavor1: id1
        ...

## Debugging

Verbosity:

    debug: true

Create APEL dumps even without enabled ssm:

    storage:
      apelSpool: /accounting/ssm

Local database export to */accounts/notebooks.db* is enabled by default. It can be disabled by setting the location to empty value:

    storage:
      notebooksDb:

## FQAN configuration

FQAN filed mapping for accounting.

By default the values are taken from *primary\_group* field (=the first matched OIDC role in hub config *allowed\_groups*).

Example (multiple values per FQAN possible, separated by comma):

    accounting:
      # default_fqan: vo.notebooks.egi.eu
      # fqan_key: primary_group
      fqan:
        vo.access.egi.eu: urn:mace:egi.eu:group:vo.access.egi.eu:role=member#aai.egi.eu
        vo.notebooks.egi.eu: urn:mace:egi.eu:group:vo.notebooks.egi.eu:role=member#aai.egi.eu
