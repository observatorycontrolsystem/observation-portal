<template>
  <panel 
    icon="fa-calendar" 
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
  
    <!-- TODO -->
    <div class="alert alert-danger" v-show="errors.non_field_errors" role="alert">
      <span v-for="error in errors.non_field_errors" :key="error">{{ error }}</span>
    </div>


    <b-container>
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
              A start time cannot be selected for a Rapid Response observation--it will be scheduled as soon as possible.
            </li>
          </ul>
          <h4 v-show="showAirmass" class="text-center">Visibility</h4>
          <airmass v-show="showAirmass" :data="airmassData" :showZoomControls="true"></airmass>
        </b-col>
        <b-col :md="show ? 6 : 12">
          <b-form>
            <customfield v-show="observation_type != 'RAPID_RESPONSE'"
              v-model="window.start" 
              type="datetime" 
              label="Start" 
              field="start" 
              desc="UT time when the observing window opens"
              :errors="errors.start" 
              @input="update"              
            />
            <customfield 
              v-model="window.end" 
              type="datetime" 
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

            <!-- TODO -->
            <a class="btn btn-info col-sm-8 col-sm-offset-4" v-on:click="genCadence" v-show="cadence != 'none'">Generate Cadence</a>

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
      customfield, 
      customselect, 
      panel, 
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
