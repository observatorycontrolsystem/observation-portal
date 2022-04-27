# Changelog

This project adheres to semantic versioning.

## [Unreleased]
### Added
- New API endpoint (`/api/users-bulk/`) to create users in bulk. This should
  come in handy when you want to speed up the account creation process for a
  known set of new users (e.g. educational users).

### Changed
-  Only send time allocation reminder email to non-educational users.

### Removed

## [4.2.3] - 2022-04-21

### Added
- Add `configuration_repeats` to Request model to allow for repeated configuration blocks for things like nodding between targets.

## [4.2.1] - 2022-03-22

Fix issue when copying a science application which has been assigned a TAC ranking

### Changed
- Set TAC ranking, TAC priority and proposal to their default values when copying a Science Application to a new draft

## [4.2.0] - 2022-03-21

Add ability to copy previous science applications for use in a new call.

### Changed
- Added copy action to ScienceApplicationViewset (`/api/scienceapplications/<pk>/copy`)
- When copying a science application, a call of the same proposal type must be open. A new draft science application will be created.

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
