# Changelog

This project adheres to semantic versioning.

## [Unreleased]
### Added
### Changed
### Removed

## [4.1.0] - 2022-03-16

We've switched from using elasticsearch to opensearch.
This just affects the telescope telemetry / status endpoints.

### Changed
- elasticsearch 5.x support updated to opensearch 1.x support
- ELASTICSEARCH_* environment variables renamed to OPENSEARCH_*

## [4.0.0] - 2022-03-01

Although this is a major version change, this should be regarded as a 
"maintenance" release. The REST API remains unchanged. However, major dependency
changes (moving to Django 4 & dropping Python 3.7 support) might cause
dependent projects to break; hence the major bump.

### Added
- Django 4.x support
- Python 3.10 support
- Project management with Poetry (pyproject.toml, etc)
- A changelog :)

### Changed

### Removed
- setup.py
- Python 3.7 support
- Django 3.x support
