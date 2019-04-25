<template>
  <panel :show="show"
    title="Request" 
    icon="fab fa-wpexplorer" 
    :id="'request' + index" 
    :index="index" 
    :errors="errors" 
    :canremove="this.index > 0" 
    :cancopy="true" 
    @remove="$emit('remove')"
    @show="show = $event"
    @copy="$emit('copy')" 
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
            <li><a target="_blank" href="https://lco.global/observatory/instruments/">More information about LCO instruments.</a></li>
          </ul>
        </b-col>
        <b-col :md="show ? 6 : 12">
          <b-form>
            <customselect v-if="!simple_interface"
              v-model="data_type" 
              label="Observation Type" 
              :options="[
                {value:'IMAGE', text: 'Image'}, 
                {value:'SPECTRA', text:'Spectrum'}
              ]"
              :errors="errors.data_type"              
              @input="update" 
            />
            <customselect 
              v-model="instrument_type" 
              label="Instrument" 
              field="instrument_type"
              :errors="errors.instrument_type" 
              :options="availableInstrumentOptions"
              @input="update" 
            />
            <customfield v-if="!simple_interface"
              v-model="request.acceptability_threshold" 
              label="Acceptability Threshold" 
              field="acceptability_threshold" 
              desc="The percentage of the observation that must be completed to mark the request as complete 
                    and avert rescheduling. The percentage should be set to the lowest value for which the 
                    amount of data is acceptable to meet the science goal of the request."
              :errors="errors.acceptability_threshold" 
              @input="update"
            />
          </b-form>
        </b-col>
      </b-row>
    </b-container>
    <configuration v-for="(configuration, idx) in request.configurations" :key="'configuration' + idx"
      :index="idx" 
      :configuration="configuration" 
      :selectedinstrument="instrument_type" 
      :datatype="data_type" 
      :data_type="data_type"
      :parentshow="show"
      :available_instruments="available_instruments"
      :errors="_.get(errors, ['configurations', idx], {})"
      :duration_data="_.get(duration_data, ['configurations', idx], {'duration':0})"
      :simple_interface="simple_interface" 
      @remove="removeConfiguration(idx)" 
      @copy="addConfiguration(idx)" 
      @generateCalibs="generateCalibs"
      @configurationupdated="configurationUpdated" 
      @configurationfillwindow="configurationFillWindow" 
    />
    <window v-for="(window, idx) in request.windows" :key="'window' + idx"
      ref="window" 
      :index="idx" 
      :window="window" 
      :errors="_.get(errors, ['windows', idx], {})" 
      :parentshow="show" 
      :simple_interface="simple_interface"
      :observation_type="observation_type"
      @remove="removeWindow(idx)" 
      @windowupdate="windowUpdated" 
      @cadence="cadence"
      @copy="addWindow(idx)"
    />
  </panel>
</template>
<script>
  import _ from 'lodash';

  import { collapseMixin, slitWidthToExposureTime } from '../utils.js';
  import configuration from './configuration.vue';
  import window from './window.vue';
  import panel from './util/panel.vue';
  import customalert from './util/customalert.vue';
  import customfield from './util/customfield.vue';
  import customselect from './util/customselect.vue';

  export default {
    props: [
      'request', 
      'index', 
      'errors', 
      'available_instruments', 
      'parentshow', 
      'duration_data', 
      'simple_interface', 
      'observation_type'
    ],
    components: {
      configuration, 
      window, 
      customfield, 
      customselect, 
      panel,
      customalert
    },
    mixins: [
      collapseMixin
    ],
    data: function() {
      return {
        show: true,
        data_type: this.instrumentToDataType(this.request.configurations[0].instrument_type),
        instrument_type: this.request.configurations[0].instrument_type
      };
    },
    computed: {
      availableInstrumentOptions: function(){
        let options = [];
        for( let i in this.available_instruments) {
          if (this.available_instruments[i].type === this.data_type) {
            options.push({value: i, text: this.available_instruments[i].name});
          }
        }
        this.update();
        return _.sortBy(options, 'text').reverse();
      },
      firstAvailableInstrument: function() {
        if (this.availableInstrumentOptions.length){
          return this.availableInstrumentOptions[0].value;
        } else {
          return '';
        }
      }
    },
    watch: {
      data_type: function() {
        if (Object.keys(this.available_instruments).length && (!this.instrument_type || this.available_instruments[this.instrument_type].type != this.data_type)) {
          this.instrument_type = this.firstAvailableInstrument;
          this.update();
        }
      },
      instrument_type: function(value) {
        if (value) {
          this.updateAcceptabilityThreshold(value);
          this.request.location.telescope_class = this.available_instruments[value].class.toLowerCase();
        }
      },
      available_instruments: function(){
        if (!this.instrument_type) {
          this.instrument_type = this.firstAvailableInstrument;
        }
      }
    },
    methods: {
      update: function() {
        this.$emit('requestupdate');
        let that = this;
        _.delay(function(){
          that.updateVisibility()
        }, 500);
      },
      updateVisibility: _.debounce(function() {
        if ('window' in this.$refs) {
          for (var windowIdx in this.$refs.window) {
            this.$refs.window[windowIdx].updateVisibility(this.request);
          }
        }
      }, 300),
      instrumentToDataType: function(value) {
        if (value.includes('NRES') || value.includes('FLOYDS')) {
          return 'SPECTRA';
        } else {
          return 'IMAGE';
        }
      },
      updateAcceptabilityThreshold: function(instrument) {
        const floydsDefaultAcceptability = 100;
        const otherDefaultAcceptability = 90;
        let currentAcceptability = this.request.acceptability_threshold;
        if (instrument === '2M0-FLOYDS-SCICAM') {
          if (currentAcceptability === '' || Number(currentAcceptability) === otherDefaultAcceptability) {
            // Initialize default value, or update the value if it was the non-floyds default - this means that the user
            // probably didn't modify the threshold (If they did modify it, it should probably stay at what they set).
            this.request.acceptability_threshold = floydsDefaultAcceptability;
          }
        } else {
          if (currentAcceptability === '' || Number(currentAcceptability) === floydsDefaultAcceptability) {
            // Initialize default value, or update accordingly.
            this.request.acceptability_threshold = otherDefaultAcceptability;
          }
        }
      },
      configurationFillWindow: function(configuration_id) {
        // TODO: This function
        console.log('configurationfillwindow');
        if ('largest_interval' in this.duration_data) {
          let num_exposures = this.request.configurations[0].instrument_configs[0].exposure_count;
          let configuration_duration = this.duration_data.configuration[configuration_id].duration;
          let available_time = this.duration_data.largest_interval - this.duration_data.duration + (configuration_duration * num_exposures);
          num_exposures = Math.floor(available_time / configuration_duration);
          this.request.configurations[configuration_id].exposure_count = Math.max(1, num_exposures);
          this.update();
        }
      },
      generateCalibs: function(configurations_id) {
        // TODO: This function
        let request = this.request;
        let calibs = [{}, {}, {}, {}];
        for(let x in calibs){
          calibs[x] = _.cloneDeep(request.configurations[configurations_id]);
          calibs[x].exposure_time = 60;
        }
        calibs[0].type = 'LAMP_FLAT'; calibs[1].type = 'ARC';
        calibs[0].guiding_config.optional = true; calibs[1].guiding_config.optional = true;
        calibs[0].instrument_configs[0].exposure_time = slitWidthToExposureTime(calibs[0].spectra_slit);
        request.configurationstatuses.unshift(calibs[0], calibs[1]);
        calibs[2].type = 'ARC'; calibs[3].type = 'LAMP_FLAT';
        calibs[2].ag_mode = 'OPTIONAL'; calibs[3].ag_mode = 'OPTIONAL';
        calibs[3].exposure_time = slitWidthToExposureTime(calibs[3].spectra_slit);
        request.configurations.push(calibs[2], calibs[3]);
        this.update();
      },
      configurationUpdated: function() {
        console.log('configurationupdated');
        this.update();
      },
      windowUpdated: function() {
        console.log('windowUpdated');
        this.update();
      },
      addWindow: function(idx) {
        let newWindow = JSON.parse(JSON.stringify(this.request.windows[idx]));
        this.request.windows.push(newWindow);
        this.update();
      },
      addConfiguration: function(idx) {
        let newConfiguration = JSON.parse(JSON.stringify(this.request.configurations[idx]));
        this.request.configurations.push(newConfiguration);
        this.update();
      },
      removeWindow: function(idx) {
        this.request.windows.splice(idx, 1);
        this.update();
      },
      removeConfiguration: function(idx) {
        this.request.configurations.splice(idx, 1);
        this.update();
      },
      cadence: function(data) {
        this.$emit('cadence', {id: this.index, request: this.request, cadence: data});
      }
    }
  };
</script>
