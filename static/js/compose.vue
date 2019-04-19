<template>
  <b-container id="app">
    <b-row>
      <b-col>
        <!-- TODO: If the same alert is brought up more than once, it will only display the first time -->
        <alert v-for="alert in alerts"
          :key="alert.msg" 
          :alertclass="alert.class" 
        >
          {{ alert.msg }}
        </alert>
      </b-col>
    </b-row>
    <b-tabs id="tabs">
      <b-tab active>
        <template slot="title">
          <i class="far fa-edit"></i> Form
        </template>
        <b-container>
          <b-row>

            <!-- TODO: If there isn't enough space for the first column, the sidenav will go to the bottom of the page -->
            <b-col cols="10">
            
              <requestgroup 
                :errors="errors" 
                :duration_data="duration_data" 
                :requestgroup="requestgroup"
                @requestgroupupdate="requestgroupUpdated"
              />
            </b-col>
            <b-col>

              <!-- TODO: The sidenav component -->
              <sidenav 
                :requestgroup="requestgroup" 
                :errors="errors"
              /> 
            </b-col>
          </b-row>
        </b-container>
      </b-tab>
      <b-tab>
        <template slot="title">
          <i class="fas fa-code"></i> API View
        </template>
        <b-container>
          <b-row>
            <b-col>

              <!-- TODO -->
              <a :href="dataAsEncodedStr" download="apiview.json" class="btn btn-default" title="download">
                <i class="fa fa-download"></i> Download as JSON
              </a>
              <pre>{{ JSON.stringify(requestgroup, null, 4) }}</pre>
              
            </b-col>
          </b-row>
        </b-container>
      </b-tab>
      <b-tab>
        <template slot="title">
          <i class="far fa-file-alt"></i> Drafts 
        </template>
        <b-container>
          <b-row>
            <b-col>

              <!-- TODO: The drafts component -->
              <drafts v-on:loaddraft="loadDraft" :tab="tab"/>

            </b-col>
          </b-row>
        </b-container>  
      </b-tab>
      <b-tab>
        <template slot="title">
          <i class="fas fa-question"></i> How to use this page
        </template>
        <b-container>
          <b-row>
            <b-col>
              <h2>Using the compose form</h2>
              <p>
                Use the form to describe the observation you would like carried out on the network.
                Sections marked with an exclamation mark <i class="fa fa-warning text-danger"></i> are incomplete or
                invalid. A complete section will be marked with a <i class="fa fa-check text-success"></i>. Only
                when all sections are marked complete can the observation be submitted.
              </p>
              <p>
                More information about each field may be found by hovering over the field label.
              </p>
              <p>
                Each section may be collapsed for a more compact view. Use the <i class="fa fa-window-minimize"></i>
                and <i class="fa fa-window-maximize"></i> buttons to control the state of the window.
              </p>
              <p>
                Some sections may be copied using the <i class="fa fa-copy"></i> button. This will duplicate
                the section and add it to your observing request. Sections can also be removed using the
                <i class="fa fa-trash"></i> button.
              </p>
              <h2>Using the API view</h2>
              <p>
                This is what your request looks like in JSON format.
              </p>
              <p>
                This code can be used to submit this observation through the Request service API.
                Using the API allows you to generate and submit observations for scheduling using
                programming languages like python.
              </p>
              <p>
                For more information see the
                <a target="_blank" href="https://developers.lco.global/#observations">API Documentation</a>
              </p>
              <h2>Loading and saving drafts</h2>
              <p>
                At any time you may save an observation request as a draft. Use the <i class="fa fa-save"></i> Save Draft
                button. Drafts can be loaded and managed from the Drafts pane. You will see drafts saved by other members
                of your proposal as well as your own.
              </p>
            </b-col>
          </b-row>
        </b-container>
      </b-tab>
      <template slot="tabs">
        <b-button-group>
          <div v-b-tooltip.hover title="Clear form">
            <b-button variant="warning" v-on:click="clear()"><i class="fa fa-times"></i> Clear</b-button>
          </div>
          <div v-b-tooltip.hover title="Save a draft of this observing request. The request will not be submitted.">
            <b-dropdown v-if="!draftExists" 
              variant="primary" 
              right 
              split
              @click="saveDraft(draftId)" 
            >
              <template slot="button-content">
                <i class="fa fa-save"></i> {{ saveDraftText }}
              </template>
              <b-dropdown-item @click="saveDraft(-1)">
                Save as new draft
              </b-dropdown-item>
            </b-dropdown>
            <b-button v-else 
              variant="primary" 
              @click="saveDraft(-1)"
            >
              <i class="fa fa-save"></i> {{ saveDraftText }}
            </b-button>
          </div>
          <div v-b-tooltip.hover title="Submit observing request">
            <b-button 
              variant="success" 
              :disabled="!_.isEmpty(errors)"
              @click="submit()" 
            >
              <i class="fa fa-check"></i> Submit
            </b-button>
          </div>
        </b-button-group>
      </template>
    </b-tabs>
  </b-container>
</template>
<script>
  import moment from 'moment';
  import _ from 'lodash';
  import $ from 'jquery';
  import Vue from 'vue';

  import requestgroup from './components/requestgroup.vue';
  import drafts from './components/drafts.vue';
  import sidenav from './components/sidenav.vue';
  import alert from './components/util/alert.vue';
  import { datetimeFormat } from './utils.js';

  export default {
    name: 'app',
    components: {
      requestgroup, 
      drafts, 
      sidenav, 
      alert
    },
    data: function() {
      return {
        tab: 1,
        draftId: -1,
        requestgroup: {
          name: '',
          proposal: '',
          ipp_value: 1.05,
          operator: 'SINGLE',
          observation_type: 'NORMAL',
          requests: [{
            acceptability_threshold: '',
            configurations: [{
              type: 'EXPOSE',
              instrument_type: '',
              fill_window: false,
              instrument_configs: [{
                bin_x: '',
                bin_y: '',
                exposure_count: 1,
                exposure_time: '',
                extra_params: {
                  defocus: 0
                },
                optical_elements: {
                  filter: ''
                }
              }],
              acquisition_config: {
                mode: '',
                extra_params: {
                  acquire_radius: null
                }
              },
              guiding_config: {
                mode: '',
                optional: true,
                extra_params: {}
              },
              target: {
                name: '',
                type: 'SIDEREAL',
                ra: '',
                dec: '',
                proper_motion_ra: 0.0,
                proper_motion_dec: 0.0,
                epoch: 2000,
                parallax: 0,
              },
              constraints: {
                max_airmass: 1.6,
                min_lunar_distance: 30.0
              }
            }],
            windows: [{
              start: moment.utc().format(datetimeFormat),
              end: moment.utc().add(1, "days").format(datetimeFormat)
            }],
            location: {
              telescope_class: ''
            }
          }]
        },
        errors: {},
        duration_data: {},
        alerts: []
      };
    },
    computed: {
      dataAsEncodedStr: function() {
        return 'data:application/json;charset=utf-8,' +  encodeURIComponent(JSON.stringify(this.requestgroup));
      },
      saveDraftText: function() {
        if (this.draftExists) {
          return "Save draft #" + this.draftId;
        } else {
          return "Save draft";
        }
      },
      draftExists: function() {
        return this.draftId > -1;
      }
    },
    methods: {
      validate: _.debounce(function() {
        let that = this;
        $.ajax({
          type: 'POST',
          url: '/api/requestgroups/validate/',
          data: JSON.stringify(that.requestgroup),
          contentType: 'application/json',
          success: function(data) {
            that.errors = data.errors;
            that.duration_data = data.request_durations;
          }
        });
      }, 200),
      submit: function() {
        let duration = moment.duration(this.duration_data.duration, 'seconds');
        let duration_string = '';
        if (duration.hours() > 0) {
          duration_string += duration.hours() + ' hours, ';
        }
        duration_string += duration.minutes() + ' minutes, ' + duration.seconds() + ' seconds';
        if (confirm('The request will take approximately ' + duration_string + ' of telescope time. Are you sure you want to submit the request?')) {
          let that = this;
          $.ajax({
            type: 'POST',
            url: '/api/requestgroups/',
            data: JSON.stringify(that.requestgroup),
            contentType: 'application/json',
            success: function(data){
              window.location = '/requestgroups/' + data.id;
            }
          });
        }
      },
      requestgroupUpdated: function() {
        console.log('requestgroup updated');
        this.validate();
      },
      saveDraft: function(id) {
        // Clear out alerts first so that only current alerts are displayed
        _.remove(this.alerts);
        if (!this.requestgroup.name || !this.requestgroup.proposal) {
          this.alerts.push({class: 'danger', msg: 'Please give your draft a title and proposal'});
          return;
        }
        let url = '/api/drafts/';
        let method = 'POST';
        if (id > -1) {
          url += id + '/';
          method = 'PUT';
        }
        let that = this;
        $.ajax({
          type: method,
          url: url,
          data: JSON.stringify({
            proposal: that.requestgroup.proposal,
            title: that.requestgroup.name,
            content: JSON.stringify(that.requestgroup)
          }),
          contentType: 'application/json',
        }).done(function(data) {
          that.draftId = data.id;
          that.alerts.push({class: 'success', msg: 'Draft id: ' + data.id + ' saved successfully'});
          console.log('Draft saved ' + that.draftId);
        }).fail(function(data) {
          for (let error in data.responseJSON.non_field_errors) {
            that.alerts.push({class: 'danger', msg: data.responseJSON.non_field_errors[error]});
          }
        });
      },
      loadDraft: function(id) {
        this.draftId = id;
        this.tab = 1;
        let that = this;
        $.getJSON('/api/drafts/' + id + '/', function(data) {
          that.requestgroup = {};
          Vue.nextTick(function() {
            that.requestgroup = JSON.parse(data.content);
          });
          that.validate();
        });
      },
      clear: function() {
        if(confirm('Clear the form?')) {
          window.location.reload();
        }
      }
    }
  };
</script>
<style>
  /* #dldjson {
    float: right;
    position: relative;
    top: 10px;
    right: 175px;
  } */
</style>
