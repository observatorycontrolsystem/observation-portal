# Changelog

This project adheres to semantic versioning.

## [Unreleased]

### Added

### Changed

### Removed
## [4.8.3] - 2023-11-29

### Changed
- Dependabot security updates

## [4.8.2] - 2023-11-09

### Changed
- Fixed URL generation for proposal invites

## [4.8.1] - 2023-09-20

### Added
- Proposal admin actions to make proposals public in bulk or extend their unused time allocations to next semester

### Changed
- Swapped out muscat diffusers for narrowband in test classes

## [4.8.0] - 2023-09-07

### Changed
- Fix /api/telescope_states to return a useful error message and 502 when no connection to OpenSearch is available.

## [4.7.2] - 2023-05-23

### Changed
- Updated invitation email to include email address in URL param
- Plumb email param for /accounts/register to registration form

## [4.5.1] - 2023-04-03

### Changed
- Expanded validation range for epoch_of_perih to allow minor planets with low values to be accepted


## [4.5.0] - 2023-03-28

### Changed
- Add proposal tags to response from semesters timeallocation action 


## [4.4.12] - 2023-03-09

### Changed
- Fixed a bug from last release causing old instrument types associated with inactive telescopes to not find their exposure parameters


## [4.4.10] - 2023-03-06

### Changed
- Add a flag for internal calls using configdb instruments to ignore instruments from 
telescopes, enclosures, or sites that are marked as active:false in ConfigDB.
- Change telescope_states api endpoint to include non-schedulable instruments in response.


## [4.4.9] - 2023-02-28

### Added
- Support for validating instrument configurations via validation schema defined in the Configuration Database's ConfigurationTypeProperties.
This allows for specific per-instrument type/per-configuration type validation of instrument configs within direct submissions to /api/schedule or via the /api/requestgroups/ endpoint.


## [4.4.8] - 2023-01-31

### Added
- time_charged field added to Configuration Status model to keep track of time charged and refunds
- Refund percentage button on Observations and Configuration Status pages in Admin interface

## [4.4.5] - 2022-12-12

### Changed
- Canceling a Request now cancels or deletes all pending Observations for that Request that are scheduled in the future

## [4.4.4] - 2022-09-12

### Added
- Add minimum value validator for max_seeing constraint

## [4.4.3] - 2022-08-01

### Added
- optimization_type field within the Request model for emphasizing TIME or AIRMASS based scheduling optimization for that request

## [4.4.2] - 2022-07-25

### Added
- Override for duration_per_exposure calculation for an instrument configuration dict of a given instrument type

## [4.4.1] - 2022-06-23

### Added
- Added range filters for /api/observations `created` datetime field

## [4.4.0] - 2022-06-14

### Changed
- Fix: accept pending proposal invites on bulk user creation

## [4.3.3] - 2022-05-31

### Added
- Added max_lunar_phase to constraints with a range of 0 to 1

### Changed
- last_scheduled timestamp is now updated on direct submissions to a site

## [4.3.2] - 2022-05-12

### Changed
- Update to work with configdb 3.0.1 changes with new telescope aperture field.
- Fix bug in configdb caching function that failed with kwargs

## [4.3.0] - 2022-04-28

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
