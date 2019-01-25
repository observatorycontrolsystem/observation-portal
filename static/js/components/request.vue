<template>
  <panel :id="'request' + index" :index="index" :errors="errors" v-on:show="show = $event"
         :canremove="this.index > 0" :cancopy="true" icon="fa-wpexplorer" title="Request" v-on:remove="$emit('remove')"
         v-on:copy="$emit('copy')" :show="show">
    <div class="alert alert-danger" v-show="errors.non_field_errors" role="alert">
      <span v-for="error in errors.non_field_errors">{{ error }}</span>
    </div>
    <div class="row">
      <div class="col-md-6 compose-help" v-show="show">
          <ul>
            <li><a target="_blank" href="https://lco.global/observatory/instruments/">More information about LCO instruments.</a></li>
          </ul>
      </div>
      <div :class="show ? 'col-md-6' : 'col-md-12'">
        <form class="form-horizontal">
           <customselect v-model="data_type" label="Observation Type" v-on:input="update" :errors="errors.data_type"
                         v-if="!simple_interface"
                         :options="[{value:'IMAGE', text: 'Image'}, {value:'SPECTRA', text:'Spectrum'}]">
          </customselect>
          <customselect v-model="instrument_name" label="Instrument" field="instrument_name"
                         :errors="errors.instrument_name" :options="availableInstrumentOptions"
                         desc="Select the instrument with which this observation will be made.">
          </customselect>
          <customfield v-model="request.acceptability_threshold" label="Acceptability Threshold" field="acceptability_threshold" v-on:input="update"
                        :errors="errors.acceptability_threshold" desc="The percentage of the observation that must be completed to mark the request as complete and avert rescheduling.
                        The percentage should be set to the lowest value for which the amount of data is acceptable to meet the science goal of the request."
                        v-if="!simple_interface">
          </customfield>
        </form>
      </div>
    </div>
    <target :target="request.target" v-on:targetupdate="targetUpdated" :datatype="data_type" :parentshow="show"
            :errors="_.get(errors, 'target', {})" :simple_interface="simple_interface"
            :selectedinstrument="instrument_name">
    </target>
    <div v-for="(molecule, idx) in request.molecules">
      <molecule :index="idx" :molecule="molecule" :selectedinstrument="instrument_name" :datatype="data_type" :parentshow="show"
                v-on:moleculeupdate="moleculeUpdated" v-on:moleculefillwindow="moleculeFillWindow" :available_instruments="available_instruments"
                :errors="_.get(errors, ['molecules', idx], {})"
                :duration_data="_.get(duration_data, ['molecules', idx], {'duration':0})"
                :simple_interface="simple_interface"
                v-on:remove="removeMolecule(idx)" v-on:copy="addMolecule(idx)" v-on:generateCalibs="generateCalibs">
      </molecule>
    </div>
    <div v-for="(window, idx) in request.windows">
      <window ref="window" :index="idx" :window="window" v-on:windowupdate="windowUpdated" v-on:cadence="cadence"
              :errors="_.get(errors, ['windows', idx], {})" :parentshow="show" :simple_interface="simple_interface"
              :observation_type="observation_type"
              v-on:remove="removeWindow(idx)" v-on:copy="addWindow(idx)">
      </window>
    </div>
    <constraints :constraints="request.constraints" v-on:constraintsupdate="constraintsUpdated" :parentshow="show" :errors="_.get(errors, 'constraints', {})" v-if="!simple_interface">
    </constraints>
  </panel>
</template>
<script>
import _ from 'lodash';

import {collapseMixin, slitWidthToExposureTime} from '../utils.js';
import target from './target.vue';
import molecule from './molecule.vue';
import window from './window.vue';
import constraints from './constraints.vue';
import panel from './util/panel.vue';
import customfield from './util/customfield.vue';
import customselect from './util/customselect.vue';

export default {
  props: ['request', 'index', 'errors', 'available_instruments', 'parentshow', 'duration_data', 'simple_interface', 'observation_type'],
  components: {target, molecule, window, constraints, customfield, customselect, panel},
  mixins: [collapseMixin],
  data: function(){
    return {
      show: true,
      data_type: this.instrumentToDataType(this.request.molecules[0].instrument_name),
      instrument_name: this.request.molecules[0].instrument_name
    };
  },
  computed: {
    availableInstrumentOptions: function(){
      var options = [];
      for(var i in this.available_instruments){
        if(this.available_instruments[i].type === this.data_type){
          options.push({value: i, text: this.available_instruments[i].name});
        }
      }
      this.update();
      return _.sortBy(options, 'text').reverse();
    },
    firstAvailableInstrument: function(){
      if(this.availableInstrumentOptions.length){
        return this.availableInstrumentOptions[0].value;
      }else{
        return '';
      }
    }
  },
  watch: {
    data_type: function(){
      if(Object.keys(this.available_instruments).length && (!this.instrument_name || this.available_instruments[this.instrument_name].type != this.data_type)){
        this.instrument_name = this.firstAvailableInstrument;
        this.update();
      }
    },
    instrument_name: function(value){
      if(value){
        this.updateAcceptabilityThreshold(value);
        this.request.location.telescope_class = this.available_instruments[value].class.toLowerCase();
      }
    },
    available_instruments: function(){
      if(!this.instrument_name){
        this.instrument_name = this.firstAvailableInstrument;
      }
    }
  },
  methods: {
    update: function(){
      this.$emit('requestupdate');
      var that = this;
      _.delay(function(){
        that.updateVisibility()
      }, 500);
    },
    updateVisibility: _.debounce(function(){
      if('window' in this.$refs) {
        for (var windowIdx in this.$refs.window) {
          this.$refs.window[windowIdx].updateVisibility(this.request);
        }
      }
    }, 300),
    instrumentToDataType: function(value){
      if (value.includes('NRES') || value.includes('FLOYDS')) {
        return 'SPECTRA';
      } else {
        return 'IMAGE';
      }
    },
    updateAcceptabilityThreshold: function(instrument) {
      const floydsDefaultAcceptability = 100;
      const otherDefaultAcceptability = 90;
      var currentAcceptability = this.request.acceptability_threshold;
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
    moleculeFillWindow: function(molecule_id){
      console.log('moleculefillwindow');
      if('largest_interval' in this.duration_data){
        var num_exposures = this.request.molecules[molecule_id].exposure_count;
        var molecule_duration = this.duration_data.molecules[molecule_id].duration;
        var available_time = this.duration_data.largest_interval - this.duration_data.duration + (molecule_duration*num_exposures);
        num_exposures = Math.floor(available_time / molecule_duration);
        this.request.molecules[molecule_id].exposure_count = Math.max(1, num_exposures);
        this.update();
      }
    },
    generateCalibs: function(molecule_id){
      var request = this.request;
      var calibs = [{}, {}, {}, {}];
      for(var x in calibs){
        calibs[x] = _.cloneDeep(request.molecules[molecule_id]);
        calibs[x].exposure_time = 60;
      }
      calibs[0].type = 'LAMP_FLAT'; calibs[1].type = 'ARC';
      calibs[0].ag_mode = 'OPTIONAL'; calibs[1].ag_mode = 'OPTIONAL';
      calibs[0].exposure_time = slitWidthToExposureTime(calibs[0].spectra_slit);
      request.molecules.unshift(calibs[0], calibs[1]);
      calibs[2].type = 'ARC'; calibs[3].type = 'LAMP_FLAT';
      calibs[2].ag_mode = 'OPTIONAL'; calibs[3].ag_mode = 'OPTIONAL';
      calibs[3].exposure_time = slitWidthToExposureTime(calibs[3].spectra_slit);
      request.molecules.push(calibs[2], calibs[3]);
      this.update();
    },
    moleculeUpdated: function(){
      console.log('moleculeupdated');
      this.update();
    },
    windowUpdated: function(){
      console.log('windowUpdated');
      this.update();
    },
    targetUpdated: function(){
      console.log('targetUpdated');
      this.update();
    },
    constraintsUpdated: function(){
      console.log('constraintsUpdated');
      this.update();
    },
    addWindow: function(idx){
      var newWindow = JSON.parse(JSON.stringify(this.request.windows[idx]));
      this.request.windows.push(newWindow);
      this.update();
    },
    addMolecule: function(idx){
      var newMolecule = JSON.parse(JSON.stringify(this.request.molecules[idx]));
      this.request.molecules.push(newMolecule);
      this.update();
    },
    removeWindow: function(idx){
      this.request.windows.splice(idx, 1);
      this.update();
    },
    removeMolecule: function(idx){
      this.request.molecules.splice(idx, 1);
      this.update();
    },
    cadence: function(data){
      this.$emit('cadence', {'id': this.index, 'request':this.request, 'cadence': data});
    }
  }
};
</script>
