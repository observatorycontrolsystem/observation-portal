<template>
  <panel :show="show"
    id="general" 
    title="General Information" 
    icon="fas fa-address-card" 
    :errors="errors" 
    :canremove="false" 
    :cancopy="false"
    @show="show = $event" 
  >  
    <customalert 
      v-for="error in errors.non_field_errors" 
      :key="error" 
      alertclass="danger" 
      :dismissible="false"
    >
      {{ error }}
    </customalert>
    <customalert
      v-show="!isMemberOfActiveProposals"
      alertclass="danger"
      :dismissible="false"
    >
      <p>
        You must be a member of a currently active proposal in order to create and submit observation requests. You can review the 
        <a href="https://lco.global/files/User_Documentation/gettingstartedonthelconetwork.latest.pdf">getting started guide</a> or 
        the <a href="https://lco.global/observatory/proposal/process/">proposal process documentation</a> to see how to become a member 
        of a proposal.
      </p>
    </customalert>
    <b-container class="p-0">
      <b-form-row>
        <b-col md="6" v-show="show">
          <h3>
            Duration of Observation Request:
            <sup 
              class="text-info"
              v-b-tooltip=tooltipConfig 
              title="The time that will be deducted from your proposal when this request completes. Includes exposure times, slew times, and instrument overheads."
              >
                ?
              </sup>
          </h3>
          <h2>{{ durationDisplay }}</h2>
          <br/>
          <div v-if="!simple_interface">
            <ul>
              <li>
                <a target="_blank" href="https://lco.global/documentation/rapid-response-mode/">More information about Rapid Response mode.</a>
              </li>
              <li>
                <a target="_blank" href="https://lco.global/files/User_Documentation/the_new_priority_factor.pdf">
                  More information about IntraProprosal Priority (IPP).
                </a>
              </li>
            </ul>
          </div>
        </b-col>
        <b-col :md="show ? 6 : 12">
          <b-form>
            <customfield 
              v-model="requestgroup.name"
              label="Title" 
              field="title" 
              :errors="errors.name"
              @input="update"
            />
            <customselect 
              v-model="requestgroup.proposal" 
              label="Proposal" 
              field="proposal"
              :errors="errors.proposal"
              :options="proposalOptions"
              @input="update" 
            />
            <customselect v-if="!simple_interface"
              v-model="requestgroup.observation_type" 
              label="Mode"
              field="observation_type" v-on:input="update"
              desc="Rapid Response (RR) requests bypass normal scheduling and are executed immediately. 
                    This mode is only available if a proposal was granted RR time."
              :errors="errors.observation_type"
              :options="[
                {value: 'NORMAL', text: 'Queue scheduled (default)'},
                {value:'RAPID_RESPONSE', text: 'Rapid Response'}
              ]"
              @input="update"
            />
            <customfield v-if="!simple_interface"
              v-model="requestgroup.ipp_value" 
              label="IPP Factor" 
              field="ipp_value"
              desc="Provide an InterProposal Priority factor for this request. Acceptable values are between 0.5 and 2.0"
              :errors="errors.ipp_value" 
              @input="update"
            />
            <span v-show="!show"> Total Duration: <strong>{{ durationDisplay }} </strong></span>
          </b-form>
        </b-col>
      </b-form-row>
    </b-container>
    <div v-for="(request, idx) in requestgroup.requests" :key="'request' + idx">
      <modal 
        :show="showCadence" 
        @close="cancelCadence" 
        @submit="acceptCadence"
        header="Generated Cadence" 
        :showAccept="cadenceRequests.length > 0"
      >
        <p>The blocks below represent the windows of the requests that will be generated if the cadence is accepted.
        These requests will replace the current request.</p>
        <p>Press Cancel to discard the cadence.</p>
        <p>Press Ok to accept the cadence. Once a cadence is accepted, the individual generated requests may be edited.</p>
        <cadence :data="cadenceRequests"/>

        <!-- TODO: Differentiate between loading data and no cadence found -->
        
        <p v-if="cadenceRequests.length < 1">
          <strong>
            A valid cadence could not be generated. Please try adjusting the jitter or period and make sure your target is visible
            within the selected window.
          </strong>
        </p>
      </modal>
      <request 
        :index="idx" 
        :request="request" 
        :available_instruments="available_instruments" 
        :parentshow="show"
        :simple_interface="simple_interface"
        :observation_type="requestgroup.observation_type"
        :errors="_.get(errors, ['requests', idx], {})"
        :duration_data="_.get(duration_data, ['requests', idx], {'duration': 0})"
        @remove="removeRequest(idx)" 
        @copy="addRequest(idx)"
        @requestupdate="requestUpdated" 
        @cadence="expandCadence"
      />
    </div>
    <modal 
      :show="showEdPopup" 
      :showCancel="false"
      @close="closeEdPopup" 
      @submit="closeEdPopup" 
    >
      <h3>Welcome to the LCO observation request page!</h3>
      <p>Using this form you can instruct the LCO telescope network to perform an astronomical observation on your behalf.</p>
      <p>Fields should be filled out from top to bottom. Some fields labels have blue question marks next to them. Hover over one of these
        question marks to view more information about that field.</p>
      <p>A field highlighted in red with means that there is a problem with the given value. An error message will be displayed below any underneath 
        a field such as this. An observation request cannot be submitted until the form is free of errors.</p>
      <p>Some elements may be copied using the <i class="fa fa-copy text-success"></i> copy button. For example: to create an RGB image you
        can copy the instrument configuration twice so that there are three, and set the filters in each accordingly.</p>
      <p>Thanks for using Las Cumbres Observatory!</p>
    </modal>
  </panel>
</template>
<script>
  import $ from 'jquery';
  import _ from 'lodash';
  import moment from 'moment';
  import Vue from 'vue';

  import modal from './util/modal.vue';
  import request from './request.vue';
  import cadence from './cadence.vue';
  import panel from './util/panel.vue';
  import customalert from './util/customalert.vue';
  import customfield from './util/customfield.vue';
  import customselect from './util/customselect.vue';
  import { QueryString, datetimeFormat, tooltipConfig } from '../utils.js';

  export default {
    props: [
      'errors', 
      'requestgroup', 
      'duration_data'
    ],
    components: { 
      request, 
      cadence, 
      modal, 
      customfield, 
      customselect, 
      panel,
      customalert
    },
    data: function() {
      return {
        show: true,
        tooltipConfig: tooltipConfig,
        showCadence: false,
        simple_interface: false,
        cadenceRequests: [],
        available_instruments: {},  // Has only the instruments that the user's proposals allow
        proposals: [],
        hasRetrievedProposals: false,
        isMemberOfActiveProposals: true,
        cadenceRequestId: -1
      };
    },
    created: function() {
      let that = this;
      let allowed_instruments = {};
      $.getJSON('/api/profile/', function(data) {
        that.proposals = data.proposals;
        that.hasRetrievedProposals = true;
        if (data.profile.simple_interface) {
          that.simple_interface = data.profile.simple_interface;
          for (let req = 0; req < that.requestgroup.requests.length; req++) {
            for (let conf = 0; conf < that.requestgroup.requests[req].configurations; conf++) {
              that.requestgroup.requests[req].configurations[conf].constraints.max_airmass = 2.0;
            }
          }
        }
        for (let ai in data.available_instrument_types) {
          if (!data.available_instrument_types[ai].includes('COMMISSIONING')) {
            allowed_instruments[data.available_instrument_types[ai]] = {};
          }
        }
      }).done(function() {
        $.getJSON('/api/instruments/', function(data) {
          for (let ai in allowed_instruments) {
            if (data[ai]) {
              allowed_instruments[ai] = data[ai];
            }
          }
          that.available_instruments = allowed_instruments;
          that.update();
        });
      }).done(function() {
        if (QueryString().requestgroupid) {
          that.fetchRequestGroup(QueryString().requestgroupid);
        }
      });
    },
    computed: {
      proposalOptions: function() {
        let options = [{'value': '', 'text': ''}];
        for (let p in this.proposals) {
          let proposal = this.proposals[p];
          if (proposal.current) {
            options.push({
              value: proposal.id,
              text: proposal.title + ' (' + proposal.id + ')'
            });
          }
        }
        return _.sortBy(options, 'text');
      },
      durationDisplay: function() {
        let duration = moment.duration(this.duration_data.duration, 'seconds');
        let durationStr = duration.hours() + ' hrs ' + duration.minutes() + ' min ' + duration.seconds() + ' sec';
        if (duration.days() > 0) {
          durationStr = duration.days() + ' days ' + durationStr;
        }
        return durationStr;
      },
      showEdPopup: function() {
        return localStorage.getItem('hasVisited') != 'true' && this.simple_interface;
      }
    },
    watch: {
      proposalOptions: function() {
        // There is always at least 1 empty option in the proposals options list 
        if (this.hasRetrievedProposals && this.proposalOptions.length < 2) {
          this.isMemberOfActiveProposals = false;
        } else {
          this.isMemberOfActiveProposals = true;
        }
      },
      'requestgroup.requests.length': function(value) {
        this.requestgroup.operator = value > 1 ? 'MANY' : 'SINGLE';
      },
      'requestgroup.observation_type': function(value) {
        // The value might be undefined at this point
        if (value) {
          for (var index = 0; index < this.requestgroup.requests.length; ++index) {
            for (var windowIndex = 0; windowIndex < this.requestgroup.requests[index].windows.length; ++windowIndex) {
              if (value === 'RAPID_RESPONSE') {
                delete this.requestgroup.requests[index].windows[windowIndex].start;
                this.requestgroup.requests[index].windows[windowIndex].end = moment.utc().add(24, 'hours').format(datetimeFormat);
              } else {
                if (!('start' in this.requestgroup.requests[index].windows[windowIndex])) {
                  this.requestgroup.requests[index].windows[windowIndex].start = moment.utc().format(datetimeFormat);
                }
              }
            }
          }
        }
      }
    },
    methods: {
      update: function() {
        this.$emit('requestgroupupdate');
      },
      requestUpdated: function() {
        console.log('request updated');
        this.update();
      },
      addRequest: function(idx) {
        let newRequest = _.cloneDeep(this.requestgroup.requests[idx]);
        this.requestgroup.requests.push(newRequest);
        this.update();
      },
      removeRequest: function(idx) {
        this.requestgroup.requests.splice(idx, 1);
        this.update();
      },
      expandCadence: function(data) {
        if (!_.isEmpty(this.errors)) {
          alert('Please make sure your request is valid before generating a cadence');
          return false;
        }
        this.cadenceRequestId = data.id;
        let payload = _.cloneDeep(this.requestgroup);
        payload.requests = [_.cloneDeep(data.request)];
        payload.requests[0].windows = [];
        payload.requests[0].cadence = data.cadence;
        let that = this;
        $.ajax({
          type: 'POST',
          url: '/api/requestgroups/cadence/',
          data: JSON.stringify(payload),
          contentType: 'application/json',
          success: function(data) {
            for (let r in data.requests) {
              that.cadenceRequests.push(data.requests[r]);
            }
          }
        });
        this.showCadence = true;
      },
      cancelCadence: function() {
        this.cadenceRequests = [];
        this.cadenceRequestId = -1;
        this.showCadence = false;
      },
      acceptCadence: function() {
        // this is a bit hacky because the UI representation of a request doesnt match what the api expects/returns
        let that = this;
        for (let r in this.cadenceRequests) {
          // all that changes in the cadence is the window, so instead of parsing what is returned we just copy the request
          // that the cadence was generated from and replace the window from what is returned.
          let newRequest = _.cloneDeep(that.requestgroup.requests[that.cadenceRequestId]);
          newRequest.windows = that.cadenceRequests[r].windows;
          delete newRequest.cadence;
          that.requestgroup.requests.push(newRequest);
        }
        // finally we remove the original request
        this.removeRequest(that.cadenceRequestId);
        if (this.requestgroup.requests.length > 1) this.requestgroup.operator = 'MANY';
        this.cadenceRequests = [];
        this.cadenceRequestId = -1;
        this.showCadence = false;
        this.update();
      },
      fetchRequestGroup: function(id) {
        let that = this;
        $.getJSON('/api/requestgroups/' + id + '/', function(data) {
          that.requestgroup.requests = [];
          Vue.nextTick(function() {
            that.requestgroup.requests = data.requests;
            that.update();
          });
        });
      },
      closeEdPopup: function() {
        localStorage.setItem('hasVisited', 'true');
      }
    }
  };
</script>
