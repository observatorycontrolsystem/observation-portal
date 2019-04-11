<template>
  <panel :id="'configurationstatus' + $parent.$parent.index + index" :index="index" :errors="errors" v-on:show="show = $event"
         :canremove="this.index > 0" :cancopy="true" icon="fa-cogs" title="Configuration" v-on:remove="$emit('remove')"
         v-on:copy="$emit('copy')" :show="show">
    <div class="alert alert-danger" v-show="errors.non_field_errors" role="alert">
      <span v-for="error in errors.non_field_errors">{{ error }}</span>
    </div>
    <div class="row">
      <div class="col-md-6 compose-help" v-show="show">
        <ul>
          <li>
            Try the
            <a href="https://lco.global/files/etc/exposure_time_calculator.html" target="_blank" >
              online Exposure Time Calculator.
            </a>
          </li>
          <li>
            For more information on the Defocus and Guiding options, see the "Getting Started" guide in the
            <a href="https://lco.global/documentation/" target="_blank" >
              Documentation section.
            </a>
          </li>
        </ul>
        <div class="row" v-show="configurationstatus.type === 'SPECTRUM'">
          <div class="col-md-12">
            <h2>Automatic generation of calibration frames</h2>
            <p>
              Since you are taking a spectrum, it is recommended you also schedule calibrations for before
              and after your exposure. Clicking 'Create calibration frames' will add four calibration configurations to this request: one arc and one flat before and one arc and one flat after
              your spectrum.
            </p>
            <a class="btn btn-default" v-on:click="generateCalibs" v-show="configurationstatus.type === 'SPECTRUM'">Create calibration frames</a>
          </div>
        </div>
      </div>
      <div :class="show ? 'col-md-6' : 'col-md-12'">
        <form class="form-horizontal">
          <customselect v-if="configurationstatus.type === 'EXPOSE'" v-model="configurationstatus.filter" label="Filter" v-on:input="update"
                        :errors="errors.filter" :options="filterOptions" desc="The filter to be used with this instrument">
          </customselect>
          <customselect v-if="configurationstatus.type === 'SPECTRUM' || configurationstatus.type === 'LAMP_FLAT' || configurationstatus.type === 'ARC'" v-model="configurationstatus.spectra_slit" label="Slit Width" v-on:input="update"
                        :errors="errors.spectra_slit" :options="filterOptions" desc="The width the of the slit to be used.">
          </customselect>
          <customfield v-model="configurationstatus.exposure_count" label="Exposure Count" field="exposure_count" v-on:input="update"
                       :errors="errors.exposure_count" desc="Number of exposures to make with this configuration. If the 'Fill' option is selected,
                       the count is set to the number of exposures (including overheads) that will fit in the observing window.">
            <div class="input-group-btn" slot="inlineButton">
              <button class="btn btn-default" type="button" style="font-size:16px" v-on:click="fillWindow"
                      :disabled="duration_data.duration > 0 ? false : true"><b>Fill</b></button>
            </div>
          </customfield>
          <customfield v-model="configurationstatus.exposure_time" label="Exposure Time" field="exposure_time" v-on:input="update"
                       :errors="errors.exposure_time" desc="Seconds">
          </customfield>
          <customfield v-model="configurationstatus.defocus" v-if="datatype != 'SPECTRA' && !simple_interface" label="Defocus" field="defocus" v-on:input="update"
                       :errors="errors.defocus" desc="Observations may be defocused to prevent the CCD from saturating on bright targets. This term describes the offset (in mm) of the secondary mirror from its default (focused) position. The limits are ± 3mm.">
          </customfield>
          <customselect v-model="configurationstatus.ag_mode" label="Guiding" field="ag_mode" v-on:input="update" v-if="!simple_interface && datatype !='SPECTRA'"
                        :errors="errors.ag_mode" desc="Guiding keeps the field stable during long exposures. If OPTIONAL is selected, then guiding is attempted, but the observations will be carried out even if guiding fails. If ON is selected, then if guiding fails, the observations will be aborted."
                        :options="[{value: 'OPTIONAL', text: 'Optional'},
                                   {value: 'OFF', text: 'Off'},
                                   {value: 'ON', text: 'On'}]">
          </customselect>
          <div class="spectra" v-if="datatype === 'SPECTRA' && !simple_interface">
            <customselect v-model="configurationstatus.type" v-if="selectedinstrument === '2M0-FLOYDS-SCICAM'" label="Type" v-on:input="update"
                          :errors="errors.type" desc="The type of exposure (allows for calibrations)."
                          :options="[{value: 'SPECTRUM', text: 'Spectrum'},
                                      {value: 'LAMP_FLAT', text: 'Lamp Flat'},
                                      {value: 'ARC', text:'Arc'}]">
            </customselect>
            <customselect v-model="configurationstatus.acquire_mode" label="Acquire Mode" v-on:input="update" :errors="errors.acquire_mode"
                          desc="The method for positioning the slit. If Brightest Object is selected, the slit is placed on the brightest object near the target coordinates."
                          v-if="configurationstatus.type === 'SPECTRUM'"
                          :options="[{value: 'WCS', text: 'On Target Coordinates'},
                                     {value: 'BRIGHTEST', text: 'On Brightest Object'}]">
            </customselect>
            <customfield v-show="configurationstatus.acquire_mode === 'BRIGHTEST'" v-model="configurationstatus.acquire_radius_arcsec" field="acquire_radius_arcsec"
                         label="Acquire Radius" v-on:input="update" :errors="errors.acquire_radius_arcsec" desc="The radius (in arcseconds) within which to search for the brightest object.">
            </customfield>
          </div>
        </form>
      </div>
    </div>
  </panel>
</template>
<script>
  import _ from 'lodash';
  import {collapseMixin, slitWidthToExposureTime} from '../utils.js';
  import panel from './util/panel.vue';
  import customfield from './util/customfield.vue';
  import customselect from './util/customselect.vue';

  export default {
    props: ['configurationstatus', 'index', 'errors', 'selectedinstrument', 'available_instruments', 'datatype', 'parentshow', 'duration_data', 'simple_interface'],
    components: {customfield, customselect, panel},
    mixins: [collapseMixin],
    data: function(){
      return {
        show: true,
        acquire_params: {
          acquire_mode: 'WCS',
          acquire_radius_arcsec: null
        }
      };
    },
    computed: {
      filterOptions: function(){
        if(this.simple_interface){
          return [
            {value: 'b', text: 'Blue'},
            {value: 'v', text: 'Green'},
            {value: 'rp', text: 'Red'}
          ];
        }else{
          let options = [{value: '', text: ''}];
          let filters = _.get(this.available_instruments, [this.selectedinstrument, 'filters'], []);
          for(let filter in filters){
            if(['Standard', 'Slit', 'VirtualSlit'].indexOf(filters[filter].type) > -1){ // TODO select on mode
              options.push({value: filter, text: filters[filter].name});
            }
          }
          return _.sortBy(options, 'text');
        }
      },
      binningsOptions: function(){
        // Binning has been removed from the ui, but may be added later.
        let options = [];
        let binnings = _.get(this.available_instruments, [this.selectedinstrument, 'binnings'], []);
        binnings.forEach(function(binning){
          options.push({value: binning, text: binning});
        });
        return options;
      },
    },
    methods: {
      update: function(){
        this.$emit('configurationstatusupdate');
      },
      binningsUpdated: function(){
        this.configurationstatus.bin_y = this.configurationstatus.bin_x;
        this.update();
      },
      fillWindow: function(){
        console.log('fillWindow');
        this.$emit('configurationstatusfillwindow', this.index);
      },
      generateCalibs: function(){
        this.$emit('generateCalibs', this.index);
      },
      setupImager: function(){
        this.configurationstatus.type = 'EXPOSE';
        this.configurationstatus.spectra_slit = undefined;
        this.acquire_params.acquire_mode = this.configurationstatus.acquire_mode;
        this.configurationstatus.acquire_mode = undefined;
        this.configurationstatus.acquire_radius_arcsec = undefined;
      },
      setupSpectrograph: function(){
        this.configurationstatus.ag_mode = 'ON';
        this.configurationstatus.filter = undefined;
      },
      setupNRES: function(){
        this.configurationstatus.type = 'NRES_SPECTRUM';
        this.setupSpectrograph();
        this.configurationstatus.acquire_mode = 'BRIGHTEST';
        this.configurationstatus.acquire_radius_arcsec = this.acquire_params.acquire_radius_arcsec;
      },
      setupFLOYDS: function(){
        this.configurationstatus.type = 'SPECTRUM';
        this.setupSpectrograph();
        this.configurationstatus.acquire_mode = this.acquire_params.acquire_mode;
        if (this.configurationstatus.acquire_mode === 'BRIGHTEST'){
          this.configurationstatus.acquire_radius_arcsec = this.acquire_params.acquire_radius_arcsec;
        }
      }
    },
    watch: {
      selectedinstrument: function(value){
        if(this.configurationstatus.instrument_name !== value){
          if(value.includes('NRES')){
            this.setupNRES();
          }
          else if(value.includes('FLOYDS')){
            this.setupFLOYDS();
          }
          this.configurationstatus.instrument_name = value;
          // wait for options to update, then set default
          let that = this;
          setTimeout(function(){
            let default_binning = _.get(
              that.available_instruments, [that.selectedinstrument, 'default_binning'], null
            );
            that.configurationstatus.bin_x = default_binning;
            that.configurationstatus.bin_y = default_binning;
            that.update();
          }, 100);
        }
      },
      datatype: function(value){
        if (value === 'SPECTRA'){
          if(this.selectedinstrument && this.selectedinstrument.includes('NRES')){
            this.setupNRES();
          }
          else{
            this.setupFLOYDS();
          }
        }
        else{
          this.setupImager();
        }
      },
      'configurationstatus.acquire_mode': function(value){
        if(value === 'BRIGHTEST'){
          this.configurationstatus.acquire_radius_arcsec = this.acquire_params.acquire_radius_arcsec;
        }
        else{
          if(typeof this.configurationstatus.acquire_radius_arcsec != undefined){
            this.acquire_params.acquire_radius_arcsec = this.configurationstatus.acquire_radius_arcsec;
            this.configurationstatus.acquire_radius_arcsec = undefined;
          }
        }
      },
      'configurationstatus.spectra_slit': function(value){
        if(this.configurationstatus.type === 'LAMP_FLAT'){
          this.configurationstatus.exposure_time = slitWidthToExposureTime(value);
        }
      },
      'configurationstatus.type': function(value){
        if(value === 'SPECTRUM' || value === 'NRES_SPECTRUM'){
          this.configurationstatus.ag_mode = 'ON';
        }
        else{
          this.configurationstatus.ag_mode = 'OPTIONAL';
        }
      }
    }
  };
</script>
