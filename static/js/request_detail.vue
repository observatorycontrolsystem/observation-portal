<template>
  <div class="row request-details">
    <div class="col-md-12">
      <b-tabs 
        content-class="mt-4" 
        no-fade 
        nav-class="nav-justified mt-3"
      >
        <b-tab 
          active 
          @click="tab = 'details'"
        >
          <template slot="title">
            <span title="Details about the observed request.">Details</span>
          </template>
          <div class="row" v-if="request.windows && request.windows.length != 0">
            <div class="col-md-12">
              <h4>Windows</h4>
              <table class="table table-sm">
                <thead class="no-top-border">
                  <tr><td><strong>Start</strong></td><td><strong>End</strong></td></tr>
                </thead>
                <tbody>
                  <tr 
                    v-for="(window, index) in request.windows" 
                    :key="'window-' + index"
                  >
                    <td>{{ window.start | formatDate }}</td><td>{{ window.end | formatDate }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="row" v-if="scheduled && scheduled.start">
            <div class="col-md-12">
              <h4>Scheduled</h4>
              <table class="table table-sm">
                <thead class="no-top-border">
                  <tr><td><strong>Start</strong></td><td><strong>End</strong></td><td><strong>Location</strong></td></tr>
                </thead>
                <tbody>
                  <tr>
                    <td>{{ scheduled.start | formatDate }}</td>
                    <td>{{ scheduled.end | formatDate }}</td>
                    <td>{{ scheduled.location }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="row">
            <div class="col-md-12">
              <h4>Configurations</h4>
              <div role="tablist">
                <b-card 
                  no-body 
                  class="mb-1" 
                  v-for="(configuration, index) in request.configurations" 
                  :key="configuration.id"
                >
                  <b-card-header header-tag="header" class="p-1 button-header" role="tab">
                    <b-button 
                      block 
                      href="#" 
                      v-b-toggle="'accordion-' + index" 
                      variant="light"
                    >
                      <b-row>
                        <b-col md="6">Type: {{ configuration.type }}</b-col>
                        <b-col md="6" v-if="configuration.target">Target: {{ configuration.target.name }}</b-col>
                        <b-col md="6" v-else>Target: None</b-col>
                      </b-row>
                    </b-button>
                  </b-card-header>
                  <b-collapse 
                    :visible="index === 0"
                    :id="'accordion-' + index" 
                    accordion="my-accordion" 
                    role="tabpanel"
                  >
                    <b-card-body>
                      <b-row>
                        <b-col md="6">
                          <h4>Target</h4>
                          <div v-if="!configuration.target">No target</div>
                          <ul v-else class="list-unstyled card-count card-column-two">
                            <li v-for="(x, idx) in configuration.target" :key="'target-' + idx">
                              <b-row v-if="configuration.target[idx] && x">
                                <b-col class="font-weight-bold text-nowrap" v-if="configuration.target[idx]">{{ idx | formatField }}</b-col>
                                <b-col v-if="x" class="text-right">
                                  <span v-if="idx === 'name'">{{ x }}</span>
                                  <span v-else>{{ x | formatValue }}</span>
                                  <em v-if="idx === 'ra'" class="text-muted"> ({{ x | raAsSexigesimal }})</em>
                                  <em v-if="idx === 'dec'" class="text-muted"> ({{ x | decAsSexigesimal }})</em>
                                </b-col>
                              </b-row>
                            </li>
                          </ul>
                          <br/>
                          <h4>Instrument Configs</h4>
                          <table class="table table-sm">
                            <thead class="no-top-border">
                              <tr>
                                <td><strong>Mode</strong></td>
                                <td><strong>Exposure Time</strong></td>
                                <td><strong>Exposure Count</strong></td>
                                <td><strong>Optical Elements</strong></td>
                              </tr>
                            </thead>
                            <tbody>
                              <tr 
                                v-for="(instrument_config, index) in configuration.instrument_configs" 
                                :key="'instrument_config-' + index"
                              >
                                <td v-if="instrument_config.mode">{{ instrument_config.mode }}</td>
                                <td v-else>N/A</td>
                                <td>{{ instrument_config.exposure_time | formatValue }}</td>
                                <td>{{ instrument_config.exposure_count | formatValue }}</td>
                                <td v-if="!isObjEmpty(instrument_config.optical_elements)">{{ instrument_config.optical_elements | formatValue }}</td>
                                <td v-else>None</td>
                              </tr>
                            </tbody>
                          </table>
                        </b-col>
                        <b-col md="6">
                          <h4>Acquisition</h4>
                          <ul class="list-unstyled card-count card-column-two">
                            <li 
                              v-for="(x, idx) in configuration.acquisition_config" 
                              :key="'acquisition-' + idx"
                            >
                              <b-row v-if="configuration.acquisition_config[idx] && x">
                                <b-col 
                                  class="font-weight-bold text-nowrap " 
                                  v-if="configuration.acquisition_config[idx]"
                                >
                                  {{ idx | formatField }}
                                </b-col>
                                <b-col v-if="x" class="text-right">
                                  <span v-if="idx === 'name'">{{ x }}</span>
                                  <span v-else-if="isObjEmpty(x) && idx==='extra_params'">None</span>
                                  <span v-else>{{ x | formatValue }}</span>
                                </b-col>
                              </b-row>
                            </li>
                          </ul>
                          <br/>
                          <h4>Guiding</h4>
                          <ul class="list-unstyled card-count card-column-two">
                            <li v-for="(x, idx) in configuration.guiding_config" :key="'guiding-' + idx">
                              <b-row v-if="configuration.guiding_config[idx] && x">
                                <b-col class="font-weight-bold text-nowrap" v-if="configuration.guiding_config[idx]">{{ idx | formatField }}</b-col>
                                <b-col v-if="x" class="text-right">
                                  <span v-if="idx === 'name'">{{ x }}</span>
                                  <span v-else-if="isObjEmpty(x) && (idx==='extra_params' || idx==='optical_elements')">None</span>
                                  <span v-else>{{ x | formatValue }}</span>
                                </b-col>
                              </b-row>
                            </li>
                          </ul>
                          <br/>
                          <h4>Constraints</h4>
                          <ul class="list-unstyled card-count card-column-two">
                            <li v-for="(x, idx) in configuration.constraints" :key="'constraints-' + idx">
                              <b-row v-if="configuration.constraints[idx] && x">
                                <b-col class="font-weight-bold text-nowrap" v-if="configuration.constraints[idx]">{{ idx | formatField }}</b-col>
                                <b-col v-if="x" class="text-right">
                                  <span v-if="isObjEmpty(x) && idx==='extra_params'">None</span>
                                  <span v-else>{{ x | formatValue }}</span>
                                </b-col>
                              </b-row>
                            </li>
                          </ul>
                        </b-col>
                      </b-row>
                    </b-card-body>
                  </b-collapse>
                </b-card>
              </div>
            </div>
          </div>
        </b-tab>
        <b-tab @click="tab = 'scheduling'">
          <template slot="title">
            <span title="Scheduling history.">Scheduling</span>
          </template>
          <observationhistory 
            v-show="observationData.length > 0" 
            :data="observationData" 
            :showPlotControls="true"
          />
          <div 
            v-show="observationData.length < 1"
            class="text-center"
          >
            <h3>This request has not been scheduled.</h3>
          </div>
        </b-tab>
        <b-tab @click="tab = 'visibility'">
          <template slot="title">
            <span title="Target Visibility.">Visibility</span>
          </template>
          <airmass_telescope_states 
            v-show="'airmass_limit' in airmassData" 
            :airmassData="airmassData"
            :telescopeStatesData="telescopeStatesData" 
            :activeObservation="activeObservation"
          />
          <p 
            v-if="!hasTarget"
            class="text-center text-secondary"
          >
            Visibility data not available
          </p>
        </b-tab>
        <b-tab @click="tab = 'data'">
          <template slot="title">
            <span title="Scheduling history.">Data</span>
          </template>
          <div class="row">
            <div 
              v-if="request.state === 'COMPLETED' && curFrame" 
              class="col-md-4"
            >
              <p 
                class="thumb-help"
              >
                Click a row in the data table to preview the file below. Click preview for a larger version.
              </p>
              <thumbnail 
                v-show="curFrame"
                :frame="curFrame" 
                width="400" 
                height="400"
              />
              <p v-show="canViewColor && curFrame">
                RVB frames found.
                <b-link 
                  @click="viewColorImage" 
                  title="Color Image"
                >
                  View color image <i class="fas fa-external-link-alt"></i>
                </b-link>
                <br/>
                <span v-show="loadingColor"><i class="fa fa-spin fa-spinner"></i> Generating color image...</span>
              </p>
            </div>
            <div :class="[(request.state === 'COMPLETED' && curFrame) ? 'col-md-8' : 'col-md-12']">
              <archivetable 
                :requestid="request.id" 
                @rowClicked="curFrame = $event" 
                @dataLoaded="frames = $event"
              />
              <br/>
            </div>
          </div>
        </b-tab>
      </b-tabs>
    </div>
  </div>
</template>
<script>
  import Vue from 'vue';
  import $ from 'jquery';
  import _ from 'lodash';

  import thumbnail from './components/thumbnail.vue';
  import archivetable from './components/archivetable.vue';
  import observationhistory from './components/observationhistory.vue';
  import airmass_telescope_states from './components/airmass_telescope_states.vue';
  import { login, getLatestFrame } from './archive.js';
  import {
    formatDate, formatField, formatValue, decimalDecToSexigesimal, decimalRaToSexigesimal
  } from './utils.js';

  Vue.filter('formatDate', function(value){
    return formatDate(value);
  });

  Vue.filter('formatField', function(value){
    return formatField(value);
  });

  Vue.filter('formatValue', function(value){
    return formatValue(value);
  });

  Vue.filter('raAsSexigesimal', function(ra){
    return decimalRaToSexigesimal(ra).str
  });
  Vue.filter('decAsSexigesimal', function(dec){
    return decimalDecToSexigesimal(dec).str
  });

  export default {
    name: 'app',
    components: {
      thumbnail, 
      archivetable, 
      observationhistory, 
      airmass_telescope_states
    },
    data: function() {
      return {
        request: {},
        scheduled: {},
        frames: [],
        curFrame: null,
        observationData: [],
        activeObservation: null,
        airmassData: {},
        telescopeStatesData: {},
        tab: 'details',
        loadingColor: false
      };
    },
    created: function() {
      let requestId = $('#request-detail').data('requestid');
      let that = this;
      login(function() {
        $.getJSON('/api/requests/' + requestId, function(data) {
          that.request = data;
          if (data.state === 'COMPLETED') {
            getLatestFrame(data.id, function(frame){
              that.curFrame = frame;
            });
          }
          if (data.windows.length === 0){
            $.getJSON('/api/requests/' + data.id + '/observations/', function(observations) {
                let location = observations[0].site + "." + observations[0].enclosure + "." + observations[0].telescope;
                that.scheduled = {start: observations[0].start, end: observations[0].end, location: location};
            });
          }
        });
      });
    },
    watch: {
      'tab': function(tab){
        if (tab === 'scheduling' && this.observationData.length === 0) {
          this.loadObservationData();
        }
        else if (tab === 'visibility') {
          if ($.isEmptyObject(this.airmassData)) {
            this.loadAirmassData();
          }
          if ($.isEmptyObject(this.telescopeStatesData)) {
            this.loadTelescopeStatesData();
            if (this.observationData.length === 0) {
              this.loadObservationData();
            }
          }
        }
      }
    },
    computed: {
      colorImage: function() {
        if (this.curFrame) {
          return 'https://thumbnails.lco.global/' + this.curFrame.id + '/?width=4000&height=4000&color=true';
        } else {
          return '';
        }
      },
      canViewColor: function() {
        let colorFilters = {
          'red': ['R', 'rp'],
          'visual': ['V'],
          'blue': ['B']
        };
        let filtersUsed = this.frames.map(function(frame) {return frame.FILTER;});
        let numColors = 0;
        for (let color in colorFilters) {
          for (let filter in colorFilters[color]) {
            if (filtersUsed.includes(colorFilters[color][filter])) {
              numColors += 1;
              break;
            }
          }
        }
        return numColors >= 3 ? true : false;
      },
      hasTarget: function() { 
        return this.request.configurations && this.request.configurations.length > 0 && !_.isEmpty(this.request.configurations[0].target);
      }
    },
    methods: {
      isObjEmpty: function(obj) {
        return $.isEmptyObject(obj);
      },
      loadObservationData: function() {
        let that = this;
        let requestId = $('#request-detail').data('requestid');
        $.getJSON('/api/requests/' + requestId + '/observations/', function(data) {
          that.observationData = data;
          for (let observationIdx in that.observationData){
            if (that.observationData[observationIdx].status === 'COMPLETED') {
              that.activeObservation = that.observationData[observationIdx];
              break;
            }
            else if (that.observationData[observationIdx].status === 'SCHEDULED') {
              that.activeObservation = that.observationData[observationIdx];
            }
          }
          for (let observationIdx in that.observationData) {
            // Add in some top level fields that make plotting easier
            let time_completed = 0.0;
            let total_time = 0.0;
            for(let configurationIdx in that.observationData[observationIdx].request.configurations){
              let configuration = that.observationData[observationIdx].request.configurations[configurationIdx];
              if (!_.isEmpty(configuration.summary)) {
                time_completed += configuration.summary.time_completed;
              }
              for (let inst_configIdx in configuration.instrument_configs) {
                let inst_config = configuration.instrument_configs[inst_configIdx];
                total_time += inst_config.exposure_time * inst_config.exposure_count;
              }
            }
            that.observationData[observationIdx].percent_completed = (time_completed / total_time) * 100.0;
            that.observationData[observationIdx].fail_reason = '';
            if (that.observationData[observationIdx].state === 'FAILED'){
              for (let configurationIdx in that.observationData[observationIdx].request.configurations) {
                let configuration = that.observationData[observationIdx].request.configurations[configurationIdx];
                if (configuration.state ==='FAILED' && !_.isEmpty(configuration.summary)) {
                  that.observationData[observationIdx].fail_reason = configuration.summary.reason;
                }
              }
            }
          }
        });
      },
      loadAirmassData: function() {
        if (this.hasTarget) {
          let that = this;
          let requestId = $('#request-detail').data('requestid');
          $.getJSON('/api/requests/' + requestId + '/airmass/', function(data) {
            that.airmassData = data;
          });
        }
      },
      loadTelescopeStatesData: function() {
        let that = this;
        let requestId = $('#request-detail').data('requestid');
        $.getJSON('/api/requests/' + requestId + '/telescope_states/', function(data) {
          that.telescopeStatesData = data;
        });
      },
      viewColorImage: function() {
        let that = this;
        this.loadingColor = true;
        $.getJSON(this.colorImage, function(data) {
          that.loadingColor = false;
          window.open(data['url'], '_blank');
        });
      }
    }
  };
</script>
<style>
  .nobreak {
    display: inline-block;
  }
  dl.twocol {
    -moz-column-count: 2;
    -webkit-column-count: 2;
    column-count: 2;
  }
  dl.twocol dt {
    width: inherit;
  }
  dl.twocol dd {
    margin-left: 160px;
  }
  .request-details {
    margin-top: 5px;
  }
  .thumb-help {
    font-style: italic;
    font-size: 0.8em;
  }
  .tab-pane {
    padding-top: 5px;
  }
</style>
