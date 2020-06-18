<template>
  <panel :show="show"
    :id="'configuration' + $parent.$parent.index + index" 
    :index="index" 
    :errors="errors" 
    :canremove="this.index > 0" 
    :cancopy="true" 
    icon="fas fa-cogs" 
    title="Configuration" 
    @remove="$emit('remove')"
    @copy="$emit('copy')" 
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
              For more information on the different options, see the "Getting Started" guide in our
              <a href="https://lco.global/documentation/" target="_blank" >
                Documentation section.
              </a>
            </li>
          </ul>

          <!-- TODO: Do not show if calibrations have been created -->
          
          <b-row 
            v-show="configuration.type === 'SPECTRUM'" 
            class="p-2"
          >
            <b-col>
              <h3>Calibration frames</h3>
              <p>
                We recommend that you schedule calibration frames with a spectrum type configuration.
                Click <em>'Create calibration frames'</em> to add four calibration configurations to this request: 
                one arc and one flat before and one arc and one flat after your spectrum.
              </p>
              <b-button @click="generateCalibs" variant="outline-info" block>
                Create calibration frames
              </b-button>
            </b-col>
          </b-row>
        </b-col>
        <b-col :md="show ? 6 : 12">
          <b-form>
            <customselect 
              v-if="!simple_interface && datatype !='SPECTRA' && guideModeOptions.length > 1"
              v-model="selectedImagerGuidingOption" 
              label="Guiding" 
              field="mode" 
              desc="Guiding keeps the field stable during long exposures. If set to Optional, then guiding is 
                    attempted but observations are carried out even if guiding fails. If set to On, 
                    observations are aborted if guiding fails."
              :errors="{}" 
              :options="guideModeOptions"
              @input="update" 
            />
            <div 
              class="configurationType" 
              v-if="!simple_interface"
            >
              <customselect 
                v-model="configuration.type" 
                label="Type" 
                desc="Normally, all Instrument Configurations are executed once, sequentially. If set to 
                      'Exposure Sequence', 'Spectrum Sequence' or 'NRES Spectrum Sequence', all 
                      Instrument Configurations are repeated in a loop for a specified duration."
                :errors="errors.type" 
                :options="configurationTypeOptions"
                @input="update"
              />
            </div>
            <div class="repeatDuration" v-if="configuration.type.includes('REPEAT')">
              <customfield 
                v-model="configuration.repeat_duration" 
                label="Duration" 
                field="repeat_duration" 
                :errors="errors.repeat_duration" 
                desc="Period (in seconds) over which to repeat Instrument Configurations. Clicking the 
                      'Fill' button increases the duration to the longest interval over which the target 
                      is visible in the observing window. This button is disabled until the entire 
                      request has passed validation."
                @input="update"
              >
                <b-input-group-append slot="inline-input">
                  <b-button
                    @click="configurationFillDuration"
                    :disabled="duration_data.duration > 0 ? false : true"
                  >
                    Fill
                  </b-button>
                </b-input-group-append>
              </customfield>
            </div>
            <div v-if="acquireModeOptions.length > 1 && !simple_interface && configuration.type !== 'LAMP_FLAT' && configuration.type !== 'ARC'">
              <customselect 
                v-model="configuration.acquisition_config.mode" 
                label="Acquire Mode" 
                desc="The method for positioning the slit or pinhole. If Brightest Object is selected, the slit/pinhole is placed 
                      on the brightest object near the target coordinates."
                :errors="{}"
                :options="acquireModeOptions"
                @input="update" 
              />
              <customfield
                v-for="field in requiredAcquireModeFields"
                :key="field"
                v-model="configuration.acquisition_config.extra_params[field]"
                :label="field | formatField"
                :errors="null"
                :desc="field | getFieldDescription"
                @input="updateAcquisitionConfigExtraParam($event, field)" 
              />
            </div>
          </b-form>
        </b-col>
      </b-row>
    </b-container>
    <instrumentconfig 
      v-for="(instrumentconfig, idx) in configuration.instrument_configs" 
      :key="idx"
      :index="idx" 
      :instrumentconfig="instrumentconfig" 
      :selectedinstrument="selectedinstrument" 
      :parentshow="show"
      :datatype="datatype"
      :configurationType="configuration.type"
      :show="show"
      :duration_data="_.get(duration_data, ['instrument_configs', idx], {'duration': 0})"
      :available_instruments="available_instruments"
      :errors="_.get(errors, ['instrument_configs', idx], {})"
      :simple_interface="simple_interface" 
      @remove="removeInstrumentConfiguration(idx)" 
      @copy="addInstrumentConfiguration(idx)" 
      @instrumentconfigupdate="instumentConfigurationUpdated" 
    />
    <target 
      :target="configuration.target" 
      :datatype="datatype" 
      :parentshow="show"
      :errors="_.get(errors, 'target', {})" 
      :simple_interface="simple_interface"
      :selectedinstrument="selectedinstrument"
      @targetupdate="targetUpdated" 
    />
    <constraints 
      v-if="!simple_interface"
      :constraints="configuration.constraints" 
      :parentshow="show" 
      :errors="_.get(errors, 'constraints', {})" 
      @constraintsupdate="constraintsUpdated" 
    />
  </panel>
</template>
<script>
  import _ from 'lodash';

  import { collapseMixin } from '../utils.js';
  import panel from './util/panel.vue';
  import customalert from './util/customalert.vue';
  import customfield from './util/customfield.vue';
  import customselect from './util/customselect.vue';
  import instrumentconfig from './instrumentconfig.vue';
  import constraints from './constraints.vue';
  import target from './target.vue';

  export default {
    props: [
      'configuration',
      'index',
      'errors', 
      'selectedinstrument', 
      'available_instruments', 
      'datatype', 
      'parentshow', 
      'duration_data', 
      'simple_interface'
    ],
    components: {
      customfield, 
      customselect, 
      panel,
      customalert,
      instrumentconfig,
      constraints,
      target
    },
    mixins: [
      collapseMixin
    ],
    data: function() {
      let currentGuideOption = 'ON';
      if (this.configuration.guiding_config.mode == 'OFF'){
        currentGuideOption = 'OFF';
      } else if (this.configuration.guiding_config.optional){
        currentGuideOption = 'OPTIONAL';
      }
      return {
        show: true,
        acquireHistory: {
          mode: '',
          extra_params: {}
        },
        selectedImagerGuidingOption: currentGuideOption,
        imagerGuidingOptions: [
          {value: 'OPTIONAL', text: 'Optional'},
          {value: 'ON', text: 'On'},
          {value: 'OFF', text: 'Off'}
        ]
      };
    },
    computed: {
      configurationTypeOptions: function() {
        if (_.get(this.available_instruments, this.selectedinstrument, {}).type === 'SPECTRA') {
          if (this.selectedinstrument.includes('NRES')) {
            return [
              {value: 'NRES_SPECTRUM', text: 'Spectrum'},
              {value: 'REPEAT_NRES_SPECTRUM', text: 'Spectrum Sequence'}
            ]
          } else {
            return [
              {value: 'SPECTRUM', text: 'Spectrum'},
              {value: 'REPEAT_SPECTRUM', text: 'Spectrum Sequence'},
              {value: 'LAMP_FLAT', text: 'Lamp Flat'},
              {value: 'ARC', text: 'Arc'}
            ]
          }
        }
        else {
          return [
            {value: 'EXPOSE', text: 'Exposure'},
            {value: 'REPEAT_EXPOSE', text: 'Exposure Sequence'}
          ]
        }
      },
      acquireModeOptions: function() {
        let options = [];
        if (this.available_instruments[this.selectedinstrument]) {
          let requiredModeFields = [];
          let modes = this.available_instruments[this.selectedinstrument].modes.acquisition.modes;
          for (let i in modes) {
            requiredModeFields = [];          
            if ('extra_params' in modes[i].validation_schema) {
              for (let j in modes[i].validation_schema.extra_params.schema) {
                requiredModeFields.push(j)
              }
            }          
            options.push({
              value: modes[i].code, 
              text: modes[i].name,
              requiredFields: requiredModeFields
            });
          }
        }
        return options;
      },
      guideModeOptions: function() {
        if (this.selectedinstrument in this.available_instruments) {
          let guideModes = [];
          for (let gm in this.available_instruments[this.selectedinstrument].modes.guiding.modes) {
            if (this.selectedinstrument != '2M0-SCICAM-MUSCAT') {
              guideModes.push({
                  text: this.available_instruments[this.selectedinstrument].modes.guiding.modes[gm].name,
                  value: this.available_instruments[this.selectedinstrument].modes.guiding.modes[gm].code,
              });
            }
            if (this.available_instruments[this.selectedinstrument].modes.guiding.modes[gm].code == 'ON'){
              guideModes.push({text: 'Optional', value: 'OPTIONAL'})
            }
          }
          return guideModes;
        } else {
          return [];
        }
      },
      requiredAcquireModeFields: function() {
        for (let i in this.acquireModeOptions) {
          if (this.acquireModeOptions[i].value == this.configuration.acquisition_config.mode) {
            return this.acquireModeOptions[i].requiredFields;
          }
        }
        return [];
      }
    },
    created: function() {
      this.setupAcquireAndGuideFieldsForType(this.configuration.type);
    },
    methods: {
      update: function() {
        this.$emit('configurationupdated');
      },
      updateAcquisitionConfigExtraParam: function(value, field) {
        if (value === '') {
          // Remove the field if an empty value is entered because the validation
          // for required extra params only check if the field exists
          this.configuration.acquisition_config.extra_params[field] = undefined;
        }
        this.update();
      },
      configurationFillDuration: function() {
        this.$emit('configurationfillduration', this.index);
      },
      generateCalibs: function() {
        this.$emit('generateCalibs', this.index);
      },
      constraintsUpdated: function() {
        console.log('constraintsUpdated');
        this.update();
      },
      targetUpdated: function() {
        console.log('targetUpdated');
        this.update();
      },
      removeInstrumentConfiguration: function(idx) {
        this.configuration.instrument_configs.splice(idx, 1);
        this.update();
      },
      addInstrumentConfiguration: function(idx) {
        let newInstrumentConfiguration = JSON.parse(JSON.stringify(this.configuration.instrument_configs[idx]));
        this.configuration.instrument_configs.push(newInstrumentConfiguration);
        this.update();
      },
      instumentConfigurationUpdated: function() {
        console.log('instrumentconfigUpdated');
        this.update();
      },
      acquisitionModeIsAvailable: function(acquisitionMode, acquisitionExtraParams) {
        // In order for a mode to be available, its code as well as any extra params must match
        let modeMatches;
        for (let amo in this.acquireModeOptions) {
          if (acquisitionMode === this.acquireModeOptions[amo].value) {
            modeMatches = true;
            for (let aep in acquisitionExtraParams) {
              if (this.acquireModeOptions[amo].requiredFields.indexOf(aep) < 0) {
                modeMatches = false;
              }
            }
            if (modeMatches) {
              return true;
            }
          }
        }
        return false;
      },
      saveAcquireFields: function() {
        if (this.configuration.acquisition_config.mode !== 'OFF') {
          this.acquireHistory.mode = this.configuration.acquisition_config.mode;
          this.acquireHistory.extra_params = this.configuration.acquisition_config.extra_params;
        }
      },
      setAcquireFields: function() {
        if (this.acquisitionModeIsAvailable(this.configuration.acquisition_config.mode, this.configuration.acquisition_config.extra_params)) {
          // The mode that is already set works!
          return;
        }
        if (this.acquireModeOptions.length < 1 || this.simple_interface) {
          // This case would happen for i.e. imagers that do not have any acquisition modes. Also
          // turn off acquisition for the simple interface since that interface only displays imager,
          // and should not be complicated.
          this.turnOffAcquisition();
          return;
        }
        let defaultMode = this.available_instruments[this.selectedinstrument].modes.acquisition.default;
        if (this.acquisitionModeIsAvailable(this.acquireHistory.mode, this.acquireHistory.extra_params)) {
          this.configuration.acquisition_config.mode = this.acquireHistory.mode;
          this.configuration.acquisition_config.extra_params = this.acquireHistory.extra_params;
        } else if (defaultMode) {
          this.configuration.acquisition_config.mode = defaultMode;
          if (defaultMode === this.acquireHistory.mode) {
            this.configuration.acquisition_config.extra_params = this.acquireHistory.extra_params;
          } else {
            this.configuration.acquisition_config.extra_params = {};
          }
        } else if (this.acquireModeOptions.length > 0) {
          this.saveAcquireFields();
          this.configuration.acquisition_config.mode = this.acquireModeOptions[0].value;
          this.configuration.acquisition_config.extra_params = {};
        }
        this.update();
      },
      turnOffAcquisition: function() {
        this.saveAcquireFields();
        this.configuration.acquisition_config.mode = 'OFF';
        this.configuration.acquisition_config.extra_params = {};
        this.update();
      },
      setGuidingFields: function(guidingOption) {
        // Set the fields in the configuration's guiding_config based on the user's chosen 
        // guiding option.
        if (guidingOption === 'OFF') {
          this.configuration.guiding_config.optional = false;
          this.configuration.guiding_config.mode = 'OFF';
        } else if (guidingOption === 'ON') {
          this.configuration.guiding_config.optional = false;
          this.configuration.guiding_config.mode = 'ON';
        } else {
          this.configuration.guiding_config.optional = true;
          this.configuration.guiding_config.mode = 'ON';
        }
        this.update();
      },
      setupAcquireAndGuideFieldsForType: function(configurationType) {
        if (configurationType) {
          if (configurationType.includes('SPECTRUM')) {
            this.setGuidingFields('ON');
            this.setAcquireFields();
          } else if (configurationType == 'LAMP_FLAT' || configurationType == 'ARC') {
            this.setGuidingFields('OPTIONAL');
            this.turnOffAcquisition();
          } else if (configurationType.includes('EXPOSE')) {
            this.setGuidingFields(this.selectedImagerGuidingOption);
            this.setAcquireFields();
          }
        }
      },
      setupImager: function() {
        this.configuration.type = 'EXPOSE';
        this.update();
      },
      setupSpectrograph: function() {
        if (this.selectedinstrument.includes('NRES')) {
          this.configuration.type = 'NRES_SPECTRUM';
        } else {
          this.configuration.type = 'SPECTRUM';
        }
        this.update();
      },
    },
    watch: {
      selectedImagerGuidingOption: function(value) {
        this.setGuidingFields(value);
      },
      selectedinstrument: function(value) {
        if (this.configuration.instrument_type !== value) {
          // Set the guide mode to OPTIONAL for muscat
          if (value == '2M0-SCICAM-MUSCAT') {
            this.selectedImagerGuidingOption = 'OPTIONAL';
          }
          if (this.datatype === 'SPECTRA') {
            // Need to set up spectrograph here because the instrument might have changed
            // from NRES to FLOYDS, which have different aquire modes and configuration types
            this.setupSpectrograph();
          }
          // The selected instrument is set in the request level in the UI, it is actually updated
          // in the request json here
          this.configuration.instrument_type = value;
          this.setupAcquireAndGuideFieldsForType(this.configuration.type);
          this.update();
        }
      },
      datatype: function(value) {
        if (value === 'SPECTRA') {
          this.setupSpectrograph();
        } else {
          this.setupImager();
        }
      },
      'configuration.acquisition_config.mode': function(newValue, oldValue) {
        if (oldValue !== 'OFF' && newValue !== 'OFF') {
          let oldExtraParams = this.configuration.acquisition_config.extra_params;
          if (newValue === this.acquireHistory.mode) {
            this.configuration.acquisition_config.extra_params = this.acquireHistory.extra_params;
          } else {
            this.configuration.acquisition_config.extra_params = {};
          }
          this.acquireHistory.mode = oldValue;
          this.acquireHistory.extra_params = oldExtraParams;
          this.update();
        }
      },
      'configuration.type': function(value) {
        this.setupAcquireAndGuideFieldsForType(value);
        if (!value.includes('REPEAT')) {
          this.configuration.repeat_duration = undefined;
        }
      }
    }
  };
</script>
