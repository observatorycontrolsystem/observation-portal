EXAMPLE_RESPONSES = {
    'requestgroups': {
        'max_allowable_ipp': {
            '2021B': {
                    'INSTRUMENT-TYPE-A': {
                    'ipp_time_available': 100.0,
                    'ipp_limit': 100.0,
                    'request_duration': 0.14722222222222223,
                    'max_allowable_ipp_value': 2.0,
                    'min_allowable_ipp_value': 0.5
                    }
                }
        },
        'validate': {
            'request_durations': {
                'requests': [
                {
                    'duration': 178,
                    'configurations': [
                    {
                        'instrument_configs': [
                        {
                            'duration': 70.0
                        }
                        ],
                        'duration': 86.0
                    }
                    ],
                    'largest_interval': 36969.77505
                }
                ],
                'duration': 178
            },
            'errors': {}
        },
        'airmass': {
            'airmass_data': {
                'site-A': {
                    'times': [
                        '2021-08-11T08:33',
                        '2021-08-11T08:43',
                    ],
                    'airmasses': [
                        3.1578956971395766,
                        2.900041850251779,
                    ]
                },
                'site-B': {
                    'times': [
                        '2021-08-11T08:00',
                        '2021-08-11T08:10',
                    ],
                    'airmasses': [
                        2.1578856971695766,
                        1.900041850251779,
                    ]
                }
            },
            'airmass_limit': 3.19
        },
        'instruments': {
            'INSTRUMENT-TYPE-A': {
                'type': 'IMAGE',
                'class': '2m0',
                'name': '2.0 meter Instrument A',
                'optical_elements': {
                'filters': [
                    {
                    'name': 'Clear',
                    'code': 'air',
                    'schedulable': 'true',
                    'default': 'false'
                    }
                ]
                },
                'modes': {
                'readout': {
                    'type': 'readout',
                    'modes': [
                    {
                        'name': 'Instrument A 2x2',
                        'overhead': 0.0,
                        'code': 'instrument_A_2',
                        'schedulable': 'true',
                        'validation_schema': {}
                    },
                    {
                        'name': 'Instrument A 1x1',
                        'overhead': 0.0,
                        'code': 'instrument_A_1',
                        'schedulable': 'true',
                        'validation_schema': {}
                    }
                    ],
                    'default': 'instrument_A_1'
                }
                },
                'default_acceptability_threshold': 90.0,
                'configuration_types': {},
                'camera_type': {
                'science_field_of_view': 7.477913345312313,
                'autoguider_field_of_view': 7.477913345312313,
                'pixel_scale': 0.244,
                'pixels_x': 1530,
                'pixels_y': 1020,
                'orientation': 0.0
                }
            }
        }
    },
    'proposals': {
        'tags': ['tagA', 'tagB', 'tagC']
    }
}
