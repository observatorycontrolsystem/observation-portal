<template>
  <panel 
    icon="fas fa-calendar" 
    title="Window" 
    :id="'window' + $parent.$parent.index + index" 
    :index="index" 
    :errors="errors" 
    :canremove="this.index > 0" 
    :cancopy="true" 
    @remove="$emit('remove')"
    @copy="$emit('copy')" :show="show"
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
    <b-container class="p-0">
      <b-row>
        <b-col md="6" v-show="show">
          <ul>
            <li>
              Try the
              <a href="https://lco.global/observatory/visibility/" title="Target Visibilty Calculator" target="_blank">
                Target Visibility Calculator.
              </a>
            </li>
            <li v-show="observation_type === 'RAPID_RESPONSE'">
              A start time cannot be selected for a Rapid Response observation-it will be scheduled as soon as possible.
            </li>
          </ul>
          <h4 v-show="showAirmass" class="text-center">Visibility</h4>
          <airmass v-show="showAirmass" :data="airmassData" :showZoomControls="true"></airmass>
        </b-col>
        <b-col :md="show ? 6 : 12">
          <b-form>
            <customdatetime v-show="observation_type != 'RAPID_RESPONSE'"
              v-model="window.start" 
              label="Start" 
              field="start" 
              desc="UT time when the observing window opens"
              :errors="errors.start" 
              @input="update"              
            />
            <customdatetime 
              v-model="window.end" 
              label="End" 
              field="end" 
              desc="UT time when the observing window closes"
              :errors="errors.end" 
              @input="update"
            />
            <customselect v-if="!simple_interface"
              v-model="cadence" 
              label="Cadence" 
              field="cadence" 
              desc="A cadence will replace your current observing window with a set of windows, one for each cycle of the cadence."
              :options="[
                {text:'None', value: 'none'}, 
                {text:'Simple Period', value:'simple'}
              ]"
            />
            <customfield v-show="cadence === 'simple'" 
              v-model="period" 
              label="Period" 
              field="period" 
              desc="Fractional hours"
              :errors="errors.period"               
              @input="update"
            />
            <customfield v-show="cadence === 'simple'"
              v-model="jitter" 
              label="Jitter" 
              field="jitter" 
              desc="Acceptable deviation (before or after) from strict period."
              :errors="errors.jitter" 
              @input="update"
            />
            <b-form-group
              v-show="cadence != 'none' && this.show"
              label-size="sm"
              label-align-sm="right"
              label-cols-sm="4"
              label=""
              label-for="cadence-button"
            >
              <b-button
                block
                id="cadence-button" 
                variant="outline-info"
                @click="genCadence"
              >
                Generate Cadence
              </b-button>
            </b-form-group>
          </b-form>
        </b-col>
      </b-row>
    </b-container>
  </panel>
</template>
<script>
  import $ from 'jquery';
  import _ from 'lodash';

  import { collapseMixin } from '../utils.js';
  import panel from './util/panel.vue';
  import customalert from './util/customalert.vue';
  import customdatetime from './util/customdatetime.vue';
  import customfield from './util/customfield.vue';
  import customselect from './util/customselect.vue';
  import airmass from './airmass.vue';

  export default {
    props: [
      'window', 
      'index', 
      'errors', 
      'parentshow', 
      'simple_interface', 
      'observation_type'
    ],
    components: {
      customdatetime,
      customfield, 
      customselect, 
      panel, 
      customalert,
      airmass
    },
    mixins: [
      collapseMixin
    ],
    data: function() {
      return {
        show: this.parentshow,
        airmassData: {},
        showAirmass: false,
        cadence: 'none',
        period: 24.0,
        jitter: 12.0
      };
    },
    methods: {
      update: function() {
        this.$emit('windowupdate');
      },
      genCadence: function() {
        this.$emit('cadence', {
          'start': this.window.start, 'end': this.window.end, 'period': this.period, 'jitter': this.jitter
        });
      },
      updateVisibility: function(req) {
        let request = _.cloneDeep(req);
        // Replace the window list with a single window with this start/end
        request['windows'] = [{start: this.window.start, end: this.window.end}];
        let that = this;
        $.ajax({
          type: 'POST',
          url: '/api/airmass/',
          data: JSON.stringify(request),
          contentType: 'application/json',
          success: function (data) {
            that.airmassData = data;
            that.showAirmass = 'airmass_limit' in data;
          }
        });
      }
    }
  };
</script>
