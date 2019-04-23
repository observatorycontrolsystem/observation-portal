<template>
    <panel :show="show"
      title="Instrument Configuration"
      icon="fas fa-cogs"
      :id="'instrumentconfig' + $parent.$parent.$parent.index + $parent.index + index"
      :index="index" 
      :errors="errors"
      :canremove="this.index > 0" 
      :cancopy="true"
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
              Try the
              <a href="https://lco.global/files/etc/exposure_time_calculator.html" target="_blank">
                online Exposure Time Calculator.
              </a>
            </li>
          </ul>
        </b-col>
        <b-col :md="show ? 6 : 12">
          <b-form>
            <!-- TODO: Validate that one is selected -->
            <customselect v-if="configuration.type === 'EXPOSE'" 
              v-model="configuration.instrument_configs[index].optical_elements.filter" 
              label="Filter" 
              :errors="{}" 
              :options="filterOptions" 
              @input="update"
            />
            <!-- TODO: options should be slit options -->
            <customselect v-if="configuration.type === 'SPECTRUM' || configuration.type === 'LAMP_FLAT' || configuration.type === 'ARC'" 
              v-model="configuration.instrument_configs[index].optical_elements.slit" 
              label="Slit Width" 
              :errors="{}" 
              :options="filterOptions" 
              desc="The width the of the slit to be used."
              @input="update"
            />
            <customfield v-model="configuration.instrument_configs[index].exposure_count" 
              label="Exposure Count" 
              field="exposure_count" 
              type="number"
              :errors="errors.exposure_count" 
              desc="If the 'Fill' option is selected the count is set to the number of exposures (including overheads) that will 
                    fit in the largest observing window."
              @input="update"
            >

              <!-- TODO: The fill window button -->
              <!-- <div class="input-group-btn" slot="inlineButton">
                <button class="btn btn-default" type="button" v-on:click="fillWindow"
                        :disabled="duration_data.duration > 0 ? false : true"><b>Fill</b></button>
              </div> -->
            
            
            </customfield>
            <customfield 
              v-model="configuration.instrument_configs[index].exposure_time" 
              label="Exposure Time" 
              field="exposure_time" 
              :errors="errors.exposure_time" 
              desc="Seconds"
              @input="update"
            />
            <!-- TODO: Validate to make sure this is a floating point number -->
            <customfield v-if="datatype != 'SPECTRA' && !simple_interface" 
              v-model="configuration.instrument_configs[index].extra_params.defocus" 
              label="Defocus" 
              field="defocus" 
              :errors="{}" 
              desc="Observations may be defocused to prevent the CCD from saturating on bright targets. This 
                    term describes the offset (in mm) of the secondary mirror from its default (focused) 
                    position. The limits are ± 3mm."
              @input="update"
            />
          </b-form>
        </b-col>
      </b-row>    
    </b-container>
  </panel>
</template>
<script>
import _ from 'lodash';

import { collapseMixin, slitWidthToExposureTime } from '../utils.js';
import customfield from './util/customfield.vue';
import customselect from './util/customselect.vue';
import panel from './util/panel.vue';
import alert from './util/alert.vue';

export default {
  props: [
    'configuration',
    'errors',
    'index',
    'simple_interface',
    'available_instruments',
    'selectedinstrument',
    'datatype',
    'show',
    'duration_data'
  ],
  components: {
    customfield,
    customselect,
    panel,
    alert
  },
  mixins: [
    collapseMixin
  ],
  computed: {
    filterOptions: function() {
      if (this.simple_interface) {
        return [
          {value: 'b', text: 'Blue'},
          {value: 'v', text: 'Green'},
          {value: 'rp', text: 'Red'}
        ];
      } else {
        let options = [{value: '', text: ''}];
        let filters = _.get(this.available_instruments, [this.selectedinstrument, 'optical_elements', 'filters'], []);
        for (let filter in filters) {
          if (filters[filter].schedulable) {
            options.push({value: filters[filter].code, text: filters[filter].name});
          }
        }
        return _.sortBy(options, 'text');
      }
    }
  },
  methods: {
    update: function() {
      this.$emit('instrumentconfigupdate');
    },
    binningsUpdated: function() {
      this.configuration.instrument_configs[this.index].bin_y = this.configuration.instrument_configs[this.index].bin_x;
      this.update();
    }
  }
}
</script>
