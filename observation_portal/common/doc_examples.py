EXAMPLE_RESPONSES = {
    'requestgroups': {
        'max_allowable_ipp': {
            '2021B': {
                '2M0-INSTRUMENT-A': {
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
            '2M0-INSTRUMENT-A': {
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
        },
        'dither': {
            'constraints': {
                'max_airmass': 1.6,
                'min_lunar_distance': 30.0
            },
            'instrument_configs': [
                {
                    'optical_elements': {
                        'filter': 'V'
                    },
                    'mode': '1m0_a_instrument_mode_1',
                    'exposure_time': 30.0,
                    'exposure_count': 1,
                    'extra_params': {
                        'bin_x': 1,
                        'bin_y': 1,
                        'offset_ra': 0,
                        'offset_dec': 0
                    }
                },
                {
                    'optical_elements': {
                        'filter': 'V'
                    },
                    'mode': '1m0_a_instrument_mode_1',
                    'exposure_time': 30.0,
                    'exposure_count': 1,
                    'extra_params': {
                        'bin_x': 1,
                        'bin_y': 1,
                        'offset_ra': 0,
                        'offset_dec': 5
                    }
                },
                {
                    'optical_elements': {
                        'filter': 'V'
                    },
                    'mode': '1m0_a_instrument_mode_1',
                    'exposure_time': 30.0,
                    'exposure_count': 1,
                    'extra_params': {
                        'bin_x': 1,
                        'bin_y': 1,
                        'offset_ra': 0,
                        'offset_dec': 10
                    }
                }
            ],
            'acquisition_config': {
                'mode': 'OFF'
            },
            'guiding_config': {
                'mode': 'ON'
            },
            'target': {
                'name': 'm33',
                'type': 'ICRS',
                'ra': 23.4621,
                'dec': 30.659942,
                'proper_motion_ra': 0.0,
                'proper_motion_dec': 0.0,
                'epoch': 2000.0,
                'parallax': 0.0
            },
            'instrument_type': '1M0-INSTRUMENT-A',
            'type': 'EXPOSE',
            'extra_params': {
                'dither_pattern': 'line'
            }
        }
    },
    'proposals': {
        'tags': ['tagA', 'tagB', 'tagC']
    }
}
