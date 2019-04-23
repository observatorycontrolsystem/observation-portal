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
    <alert 
      v-for="error in errors.non_field_errors" 
      :key="error" 
      alertclass="danger" 
      :dismissible="false"
    >
      {{ error }}
    </alert>
    <b-container class="p-0">
      <b-row>
        <b-col md="6" v-show="show">
          <ul>
            <li>
              For more information on the Defocus and Guiding options, see the "Getting Started" guide in the
              <a href="https://lco.global/documentation/" target="_blank" >
                Documentation section.
              </a>
            </li>
          </ul>
        </b-col>
        <b-col :md="show ? 6 : 12">
          <b-form>
            <customselect v-if="!simple_interface && datatype !='SPECTRA'"
              v-model="configuration.guiding_config.optional" 
              label="Guiding" 
              field="mode" 
              desc="Guiding keeps the field stable during long exposures. If set to optional, then guiding is 
                    attempted but observations are carried out even if guiding fails. If set to on, 
                    observations are aborted if guiding fails."
              :errors="_.get(errors, ['guiding_config', 'optional'], {})" 
              :options="[
                {value: true, text: 'Optional'},
                {value: false, text: 'On'},
              ]"
              @input="update" 
            />
            <div class="spectra" v-if="datatype === 'SPECTRA' && !simple_interface">
              <customselect  v-if="selectedinstrument === '2M0-FLOYDS-SCICAM'" 
                v-model="configuration.type" 
                label="Type" 
                desc="The type of exposure (allows for calibrations)"
                :errors="errors.type" 
                :options="[
                  {value: 'SPECTRUM', text: 'Spectrum'},
                  {value: 'LAMP_FLAT', text: 'Lamp Flat'},
                  {value: 'ARC', text:'Arc'}
                ]"
                @input="update"
              />
              <customselect v-if="configuration.type === 'SPECTRUM'"
                v-model="configuration.acquisition_config.mode" 
                label="Acquire Mode" 
                desc="The method for positioning the slit. If Brightest Object is selected, the slit is placed 
                      on the brightest object near the target coordinates."
                :errors="{}"
                :options="[
                  {value: 'WCS', text: 'On Target Coordinates'},
                  {value: 'BRIGHTEST', text: 'On Brightest Object'}
                ]"
                @input="update" 
              />
              <customfield v-show="configuration.acquisition_config.mode === 'BRIGHTEST'" 
                v-model="configuration.acquisition_config.extra_params.acquire_radius" 
                field="acquire_radius_arcsec"
                label="Acquire Radius" 
                desc="The radius in arcseconds within which to search for the brightest object."
                :errors="{}" 
                @input="update" 
              />
            </div>
          </b-form>
        </b-col>
      </b-row>
    </b-container>
    <target 
      :target="configuration.target" 
      :datatype="data_type" 
      :parentshow="show"
      :errors="_.get(errors, 'target', {})" 
      :simple_interface="simple_interface"
      :selectedinstrument="selectedinstrument"
      @targetupdate="targetUpdated" 
    />
    <instrumentconfig v-for="(instrumentconfig, idx) in configuration.instrument_configs" :key="idx"
      :index="idx" 
      :configuration="configuration" 
      :selectedinstrument="selectedinstrument" 
      :parentshow="show"
      :datatype="datatype"
      :show="show"
      :duration_data="duration_data"
      :available_instruments="available_instruments"
      :errors="_.get(errors, ['instrument_configs', idx], {})"
      :simple_interface="simple_interface" 
      @remove="removeInstrumentConfiguration(idx)" 
      @copy="addInstrumentConfiguration(idx)" 
      @generateCalibs="generateCalibs"
      @instrumentconfigupdate="instumentConfigurationUpdated" 
    />
    <constraints v-if="!simple_interface"
      :constraints="configuration.constraints" 
      :parentshow="show" 
      :errors="_.get(errors, 'constraints', {})" 
      @constraintsupdate="constraintsUpdated" 
    />
  </panel>
</template>
<script>
  import _ from 'lodash';

  import { collapseMixin, slitWidthToExposureTime } from '../utils.js';
  import panel from './util/panel.vue';
  import alert from './util/alert.vue';
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
      'simple_interface',
      'data_type'
    ],
    components: {
      customfield, 
      customselect, 
      panel,
      alert,
      instrumentconfig,
      constraints,
      target
    },
    mixins: [
      collapseMixin
    ],
    data: function(){
      return {
        show: true,
        acquire_params: {
          mode: 'WCS',
          radius: null
        }
      };
    },
    computed: {
      availableInstrumentOptions: function() {
        let options = [];
        for( let i in this.available_instruments) {
          if (this.available_instruments[i].type === this.data_type) {
            options.push({value: i, text: this.available_instruments[i].name});
          }
        }
        this.update();
        return _.sortBy(options, 'text').reverse();
      }
    },
    methods: {
      update: function() {
        this.$emit('configurationupdated');
      },
      // fillWindow: function() {
      //   console.log('fillWindow');
      //   this.$emit('configurationfillwindow', this.index);
      // },
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
        console.log('instrumentconfig updated');
        this.update();
      },
      setupImager: function() {
        this.configuration.type = 'EXPOSE';
        // this.configuration.spectra_slit = undefined;
        this.acquire_params.mode = this.configuration.acquisition_config.mode;
        this.configuration.acquisition_config.mode = undefined;
        this.configuration.acquisition_config.extra_params.acquire_radius = undefined;
      },
      setupSpectrograph: function(){
        this.configuration.guiding_config.mode = 'ON';
        for (let ic in this.configuration.instrument_configs) {
          this.configuration.instrument_configs[ic].optical_elements.filter = undefined;
        }
      },
      setupNRES: function(){
        this.configuration.type = 'NRES_SPECTRUM';
        this.setupSpectrograph();
        this.configuration.acquisition_config.mode = 'BRIGHTEST';
        this.configuration.acquisition_config.extra_params.acquire_radius = this.acquire_params.radius;
      },
      setupFLOYDS: function(){
        this.configuration.type = 'SPECTRUM';
        this.setupSpectrograph();
        this.configuration.acquisition_config.mode = this.acquire_params.mode;
        if (this.configuration.acquisition_config.mode === 'BRIGHTEST'){
          this.configuration.extra_parmas.acquire_radius = this.acquire_params.radius;
        }
      }
    },
    watch: {
      selectedinstrument: function(value) {
        if (this.configuration.instrument_type !== value) {
          if (value.includes('NRES') ){
            this.setupNRES();
          } else if (value.includes('FLOYDS') ){
            this.setupFLOYDS();
          }
          this.configuration.instrument_type = value;
          // wait for options to update, then set default
          let that = this;
          setTimeout(function() {
            let default_binning = _.get(
              that.available_instruments, [that.selectedinstrument, 'default_binning'], null
            );
            // TODO: bin is in instrument config
            that.configuration.instrument_configs[0].bin_x = default_binning;
            that.configuration.instrument_configs[0].bin_y = default_binning;
            that.update();
          }, 100);
        }
      },
      datatype: function(value) {
        if (value === 'SPECTRA') {
          if (this.selectedinstrument && this.selectedinstrument.includes('NRES')) {
            this.setupNRES();
          } else {
            this.setupFLOYDS();
          }
        } else {
          this.setupImager();
        }
      },
      'configuration.acquisition_config.mode': function(value) {
        if (value === 'BRIGHTEST') {
          this.configuration.acquisition_config.extra_params.acquire_radius = this.acquire_params.radius;
        } else {
          if (typeof this.configuration.acquisition_config.extra_params.acquire_radius != undefined) {
            this.acquire_params.radius = this.configuration.acquisition_config.extra_params.acquire_radius;
            this.configuration.acquisition_config.extra_params.acquire_radius = undefined;
          }
        }
      },
      // TODO: This below, move stuff into instrument configs
      'configuration.spectra_slit': function(value) {
        if (this.configuration.type === 'LAMP_FLAT') {
          this.configuration.instrument_configs[0].exposure_time = slitWidthToExposureTime(value);
        }
      },
      'configuration.type': function(value) {
        if (value === 'SPECTRUM' || value === 'NRES_SPECTRUM') {
          this.configuration.guiding_config.optional = false;
          this.configuration.guiding_config.mode = 'ON'
        } else {
          this.configuration.guiding_config.optional = true;
        }
      }
    }
  };
</script>
