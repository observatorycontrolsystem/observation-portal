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
            <customselect 
              v-if="!simple_interface"
              v-model="data_type" 
              label="Observation Type" 
              :options="dataTypeOptions"
              :errors="{}"              
              @input="update" 
            />
            <customselect 
              v-model="instrument_type" 
              label="Instrument" 
              field="instrument_type"
              :errors="_.get(errors, ['configurations', 0, 'instrument_type'], {})" 
              :options="availableInstrumentOptions"
              @input="update" 
            />
            <customfield 
              v-if="!simple_interface"
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
      :parentshow="show"
      :available_instruments="available_instruments"
      :errors="_.get(errors, ['configurations', idx], {})"
      :duration_data="_.get(duration_data, ['configurations', idx], {'duration': 0})"
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
        data_type: '',
        dataTypeOptions: [],
        instrument_type: this.request.configurations[0].instrument_type
      };
    },
    computed: {
      availableInstrumentOptions: function() {
        let options = [];
        for (let ai in this.available_instruments) {
          if (this.available_instruments[ai].type === this.data_type) {
            options.push({value: ai, text: this.available_instruments[ai].name});
          }
        }
        this.update();
        return _.sortBy(options, 'text').reverse();
      },
      firstAvailableInstrument: function() {
        if (this.availableInstrumentOptions.length) {
          return this.availableInstrumentOptions[0].value;
        } else {
          return '';
        }
      }
    },
    created: function() {
      // Need to call this here for when a request is copied
      this.updateDataTypeOptions();
    },
    watch: {
      data_type: function(value) {
        if (Object.keys(this.available_instruments).length && (!this.instrument_type || this.available_instruments[this.instrument_type].type !== value)) {
          this.instrument_type = this.firstAvailableInstrument;
          this.update();
        }
      },
      instrument_type: function(newValue, oldValue) {
        if (newValue) {
          this.updateAcceptabilityThreshold(newValue, oldValue);
          this.request.location.telescope_class = this.available_instruments[newValue].class.toLowerCase();
          this.update();
        }
      },
      available_instruments: function(value) {
        if (!this.instrument_type) {
          this.instrument_type = this.firstAvailableInstrument;
        }
        this.updateDataTypeOptions();
      }
    },
    methods: {
      update: function() {
        this.$emit('requestupdate');
        let that = this;
        _.delay(function() {
          that.updateVisibility();
        }, 500);
      },
      updateVisibility: _.debounce(function() {
        if ('window' in this.$refs) {
          for (var windowIdx in this.$refs.window) {
            this.$refs.window[windowIdx].updateVisibility(this.request);
          }
        }
      }, 300),
      updateDataTypeOptions: function() {
        if (_.isEmpty(this.dataTypeOptions)) {
          let hasImage = false;
          let hasSpectra = false;
          for (let itype in this.available_instruments) {
            if (this.available_instruments[itype].type === 'IMAGE') hasImage = true; 
            if (this.available_instruments[itype].type === 'SPECTRA') hasSpectra = true;
          }
          if (hasImage) this.dataTypeOptions.push({value:'IMAGE', text: 'Image'});
          if (hasSpectra) this.dataTypeOptions.push({value:'SPECTRA', text:'Spectrum'});
          this.setDataType();
        }
      },
      setDataType: function() {
        if (this.instrument_type) {
          for (let itype in this.available_instruments) {
            if (itype === this.instrument_type) {
              this.data_type = this.available_instruments[itype].type;
              return;
            }
          }
        } else if (this.dataTypeOptions.length > 0) {
          this.data_type = this.dataTypeOptions[0].value;
        }
      },
      updateAcceptabilityThreshold: function(new_instrument_type, old_instrument_type) {
        let newDefaultAcceptability = 90;
        let oldDefaultAcceptability = 90;
        if (new_instrument_type in this.available_instruments) {
          newDefaultAcceptability = this.available_instruments[new_instrument_type].default_acceptability_threshold;
        }
        if (old_instrument_type in this.available_instruments) {
          oldDefaultAcceptability = this.available_instruments[old_instrument_type].default_acceptability_threshold;
        }
        let currentAcceptability = this.request.acceptability_threshold;
        if (currentAcceptability === '' || Number(currentAcceptability) === oldDefaultAcceptability) {
          // Initialize default value, or update the value if it was not set to the default of the 
          // previous instrument type - this means that the user probably didn't modify the threshold 
          // (If they did modify it, it should probably stay at what they set).
          this.request.acceptability_threshold = newDefaultAcceptability;
          this.update();
        }
      },
      configurationFillWindow: function(ids) {
        // TODO: This function
        console.log('configurationfillwindow');
        if ('largest_interval' in this.duration_data) {
          var num_exposures = this.request.configurations[ids.configId].instrument_configs[ids.instrumentconfigId].exposure_count;
          var configuration_duration = this.duration_data.configurations[ids.configId].duration;
          var available_time = this.duration_data.largest_interval - this.duration_data.duration + (configuration_duration * num_exposures);
          num_exposures = Math.floor(available_time / configuration_duration);
          this.request.configurations[ids.configId].instrument_configs[ids.instrumentconfigId].exposure_count = Math.max(1, num_exposures);
          this.update();
        }
      },
      generateCalibs: function(configuration_id) {
        let request = this.request;
        let calibs = [{}, {}, {}, {}];
        for (let c in calibs) {
          calibs[c] = _.cloneDeep(request.configurations[configuration_id]);
          for (let ic in calibs[c].instrument_configs) {
            calibs[c].instrument_configs[ic].exposure_time = 60;
          }
        }
        calibs[0].type = 'LAMP_FLAT'; calibs[1].type = 'ARC';
        calibs[0].guiding_config.optional = true; calibs[1].guiding_config.optional = true;
        calibs[0].guiding_config.mode = 'ON'; calibs[1].guiding_config.mode = 'ON';
        for (let ic in calibs[0].instrument_configs) {
          calibs[0].instrument_configs[ic].exposure_time = slitWidthToExposureTime(calibs[0].instrument_configs[ic].optical_elements.slit);
        }
        request.configurations.unshift(calibs[0], calibs[1]);
        calibs[2].type = 'ARC'; calibs[3].type = 'LAMP_FLAT';
        calibs[2].guiding_config.optional = true; calibs[3].guiding_config.optional = true;
        calibs[2].guiding_config.mode = 'ON'; calibs[3].guiding_config.mode = 'ON';
        for (let ic in calibs[3].instrument_configs) {
          calibs[3].instrument_configs[ic].exposure_time = slitWidthToExposureTime(calibs[3].instrument_configs[ic].optical_elements.slit);
        }
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
