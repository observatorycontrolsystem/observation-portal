<template>
  <panel id="general" :errors="errors" v-on:show="show = $event" :canremove="false" :cancopy="false"
         icon="fa-id-card-o" title="General Information" :show="show">
    <div v-for="error in errors.non_field_errors" class="alert alert-danger" role="alert">{{ error }}</div>
      <div class="row">
        <div class="col-md-6 compose-help" v-show="show">
          <h3>
            Duration of Observing Request:
            <sup><a id="durationtip" title="The time that will be deducted from your proposal when this request is completed. Includes exposure times, slew times, and instrument overheads.">?</a></sup>
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
        </div>
        <div :class="show ? 'col-md-6' : 'col-md-12'">
          <form class="form-horizontal">
            <customfield v-model="userrequest.group_id" label="Title" field="title" v-on:input="update" :errors="errors.group_id" desc="Provide a name for this observing request.">
            </customfield>
            <customselect v-model="userrequest.proposal" label="Proposal" field="proposal"
                          v-on:input="update" :errors="errors.proposal" :options="proposalOptions"
                          desc="Select the proposal for which this observation will be made.">
            </customselect>
            <customselect v-model="userrequest.observation_type" label="Mode"
                          field="observation_type" v-on:input="update"
                          :errors="errors.observation_type"
                          v-if="!simple_interface"
                          :options="[{value: 'NORMAL', text: 'Queue scheduled (default)'},
                                     {value:'TARGET_OF_OPPORTUNITY', text: 'Rapid Response'}]"
                          desc="Rapid Response (RR) requests bypass normal scheduling and are executed immediately. This mode is only available if a proposal was granted RR time.">
            </customselect>
            <customfield v-model="userrequest.ipp_value" label="IPP Factor" field="ipp_value"
                         v-on:input="update" :errors="errors.ipp_value" v-if="!simple_interface"
                         desc="Provide an InterProposal Priority factor for this request. Acceptable values are between 0.5 and 2.0">
            </customfield>
            <div class="collapse-inline" v-show="!show">Total Duration: <strong>{{ durationDisplay }}</strong></div>
          </form>
        </div>
      </div>
      <div v-for="(request, idx) in userrequest.requests">
        <modal :show="showCadence" v-on:close="cancelCadence" v-on:submit="acceptCadence"
               header="Generated Cadence" :showAccept="cadenceRequests.length > 0">
          <p>The blocks below represent the windows of the requests that will be generated if the current cadence is accepted.
          These requests will replace the current request.</p>
          <p>Press cancel to discard the cadence. Once a cadence is accepted, the individual generated requests may be edited.</p>
          <cadence :data="cadenceRequests"></cadence>
          <p v-if="cadenceRequests.length < 1"><strong>
            A valid cadence could not be generated. Please try adjusting jitter or period and make sure your target is visible
            during the selected window.
          </strong></p>
        </modal>
        <request :index="idx" :request="request" :available_instruments="available_instruments" :parentshow="show"
                 v-on:requestupdate="requestUpdated" v-on:cadence="expandCadence"
                 :simple_interface="simple_interface"
                 :observation_type="userrequest.observation_type"
                 :errors="_.get(errors, ['requests', idx], {})"
                 :duration_data="_.get(duration_data, ['requests', idx], {'duration': 0})"
                 v-on:remove="removeRequest(idx)" v-on:copy="addRequest(idx)">
        </request>
        <div class="request-margin"></div>
      </div>
    </div>
    <modal :show="showEdPopup" v-on:close="closeEdPopup" v-on:submit="closeEdPopup" :showCancel=false>
      <h3>Welcome to the LCO observation request page!</h3>
      <p>Using this form you can instruct the LCO telescope network to perform an astronomical observation on your behalf.</p>
      <p>Fields should be filled out from top to bottom. If you need help understanding a field, hovering your
          cursor over the field name will reveal additional information.</p>
      <p>A field highlighted in red means that there is a problem with the given value. Additionally, errors will appear on the right
          hand side in the request index. An observation request cannot be submitted until there are no errors.</p>
      <p>Some elements may be copied using the <i class="fa fa-copy text-success"></i> copy button. For example: to create a RGB image you
          can copy the configuration twice so that there are three, and set the filters appropriately.</p>
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
import customfield from './util/customfield.vue';
import customselect from './util/customselect.vue';
import {QueryString} from '../utils.js';
import {datetimeFormat} from '../utils.js';

export default {
  props: ['errors', 'userrequest', 'duration_data'],
  components: {request, cadence, modal, customfield, customselect, panel},
  data: function(){
    return {
      show: true,
      showCadence: false,
      simple_interface: false,
      cadenceRequests: [],
      available_instruments: {},
      proposals: [],
      cadenceRequestId: -1
    };
  },
  created: function(){
    var that = this;
    var allowed_instruments = {};
    $.getJSON('/api/profile/', function(data){
      that.proposals = data.proposals;
      if(data.profile.simple_interface){
        that.simple_interface = data.profile.simple_interface;
        for (var i = 0; i < that.userrequest.requests.length; i++) {
          that.userrequest.requests[i].constraints.max_airmass = 2.0
        }
      }
      for(var ai in data.available_instrument_types){
        if(!data.available_instrument_types[ai].includes('COMMISSIONING')){
          allowed_instruments[data.available_instrument_types[ai]] = {};
        }
      }
    }).done(function(){
      $.getJSON('/api/instruments/', function(data){
        for(var ai in allowed_instruments){
          if(data[ai]){
            allowed_instruments[ai] = data[ai];
          }
        }
        that.available_instruments = allowed_instruments;
        that.update();
      });
    }).done(function(){
      if(QueryString().userrequestid){
        that.fetchUserRequest(QueryString().userrequestid);
      }
    });
  },
  mounted: function(){
    $('#durationtip').tooltip({trigger: 'hover click'});
  },
  computed:{
    proposalOptions: function(){
      var options = [{'value': '', 'text': ''}];
      for(var p in this.proposals){
        var proposal = this.proposals[p];
        if(proposal.current){
          options.push({'value': proposal.id, 'text': proposal.title + ' (' + proposal.id + ')'});
        }
      }
      return _.sortBy(options, 'text');
    },
    durationDisplay: function(){
      var duration = moment.duration(this.duration_data.duration, 'seconds');
      var durationStr = duration.hours() + ' hrs ' + duration.minutes() + ' min ' + duration.seconds() + ' sec';
      if(duration.days() > 0){
        durationStr = duration.days() + ' days ' + durationStr;
      }
      return durationStr;
    },
    showEdPopup: function(){
      return localStorage.getItem('hasVisited') != 'true' && this.simple_interface;
    }
  },
  watch: {
    'userrequest.requests.length': function(value){
      this.userrequest.operator = value > 1 ? 'MANY' : 'SINGLE';
    },
    'userrequest.observation_type': function(value){
      for (var index = 0; index < this.userrequest.requests.length; ++index) {
        for (var windowIndex = 0; windowIndex < this.userrequest.requests[index].windows.length; ++windowIndex) {
          if (value === 'TARGET_OF_OPPORTUNITY'){
            delete this.userrequest.requests[index].windows[windowIndex].start;
            this.userrequest.requests[index].windows[windowIndex].end = moment.utc().add('hours', 6).format(datetimeFormat);
          }
          else{
            if (!('start' in this.userrequest.requests[index].windows[windowIndex])) {
              this.userrequest.requests[index].windows[windowIndex].start = moment.utc().format(datetimeFormat);
            }
          }
        }
      }
    }
  },
  methods: {
    update: function(){
      this.$emit('userrequestupdate');
    },
    requestUpdated: function(){
      console.log('request updated');
      this.update();
    },
    addRequest: function(idx){
      var newRequest = _.cloneDeep(this.userrequest.requests[idx]);
      this.userrequest.requests.push(newRequest);
      this.update();
    },
    removeRequest: function(idx){
      this.userrequest.requests.splice(idx, 1);
      this.update();
    },
    expandCadence: function(data){
      if(!_.isEmpty(this.errors)){
        alert('Please make sure your request is valid before generating a cadence');
        return false;
      }
      this.cadenceRequestId = data.id;
      var payload = _.cloneDeep(this.userrequest);
      payload.requests = [_.cloneDeep(data.request)];
      payload.requests[0].windows = [];
      payload.requests[0].cadence = data.cadence;
      var that = this;
      $.ajax({
        type: 'POST',
        url: '/api/userrequests/cadence/',
        data: JSON.stringify(payload),
        contentType: 'application/json',
        success: function(data){
          for(var r in data.requests){
            that.cadenceRequests.push(data.requests[r]);
          }
        }
      });
      this.showCadence = true;
    },
    cancelCadence: function(){
      this.cadenceRequests = [];
      this.cadenceRequestId = -1;
      this.showCadence = false;
    },
    acceptCadence: function(){
      // this is a bit hacky because the UI representation of a request doesnt match what the api expects/returns
      var that = this;
      for(var r in this.cadenceRequests){
        // all that changes in the cadence is the window, so instead of parsing what is returned we just copy the request
        // that the cadence was generated from and replace the window from what is returned.
        var newRequest = _.cloneDeep(that.userrequest.requests[that.cadenceRequestId]);
        newRequest.windows = that.cadenceRequests[r].windows;
        delete newRequest.cadence;
        that.userrequest.requests.push(newRequest);
      }
      // finally we remove the original request
      this.removeRequest(that.cadenceRequestId);
      if(this.userrequest.requests.length > 1) this.userrequest.operator = 'MANY';
      this.cadenceRequests = [];
      this.cadenceRequestId = -1;
      this.showCadence = false;
      this.update();
    },
    fetchUserRequest: function(id){
      var that = this;
      $.getJSON('/api/userrequests/' + id + '/', function(data){
        that.userrequest.requests = [];
        Vue.nextTick(function(){
          that.userrequest.requests = data.requests;
          that.update();
        });
      });
    },
    closeEdPopup: function(){
      localStorage.setItem('hasVisited', 'true');
    }
  }
};
</script>
