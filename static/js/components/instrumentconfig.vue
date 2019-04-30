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
              <a href="https://lco.global/files/etc/exposure_time_calculator.html" target="_blank">
                online Exposure Time Calculator.
              </a>
            </li>
          </ul>
        </b-col>
        <b-col :md="show ? 6 : 12">
          <b-form>
            <customfield 
              v-model="instrumentconfig.exposure_count" 
              label="Exposure Count" 
              field="exposure_count" 
              type="number"
              :errors="errors.exposure_count" 
              desc="If the 'Fill' option is selected the count is set to the number of exposures (including overheads) that will 
                    fit in the largest observing window."
              @input="update"
            >
              <b-input-group-append slot="inline-input">
                <b-button
                  @click="instrumentConfigurationfillWindow"
                  :disabled="duration_data.duration > 0 ? false : true"
                >
                  Fill
                </b-button>
              </b-input-group-append>
            </customfield>
            <customfield 
              v-model="instrumentconfig.exposure_time" 
              label="Exposure Time" 
              field="exposure_time" 
              :errors="errors.exposure_time" 
              desc="Seconds"
              @input="update"
            >
            <div 
              slot="extra-help-text"
              v-if="suggestedLampFlatSlitExposureTime" 
            >
              Suggested exposure time for a Lamp Flat with 
              slit {{ instrumentconfig.optical_elements.slit }} 
              is <strong>{{ suggestedLampFlatSlitExposureTime }} seconds</strong>
            </div>              
            </customfield>
            <customselect
              v-if="readoutModeOptions.length > 1"
              v-model="instrumentconfig.mode"
              label="Readout Mode"
              field="readout_mode"
              :options="readoutModeOptions"
              :errors="errors.mode"
              @input="update"
            />
            <div 
              v-for="opticalElementGroup in availableOpticalElementGroups"
              :key="opticalElementGroup.type"
            >
              <customselect
                v-model="instrumentconfig.optical_elements[opticalElementGroup.type]"
                :label="opticalElementGroup.label"
                :field="opticalElementGroup.type"
                :options="opticalElementGroup.options"
                :errors="{}"
                @input="updateOpticalElement"
              />
            </div>
            <div v-if="showSlitPosition">
              <customselect 
                v-model="instrumentconfig.rot_mode" 
                label="Slit Position" 
                field="rot_mode" 
                :errors="errors.rot_mode"
                :options="[
                  {value: 'VFLOAT', text: 'Parallactic'}, 
                  {value: 'SKY', text: 'User Specified'}
                ]"
                desc="With the slit at the parallactic angle, atmospheric dispersion is along the slit."
                @input="update" 
              />

              <!-- TODO: Validate angle -->
              
              <customfield 
                v-if="instrumentconfig.rot_mode === 'SKY'"
                v-model="rot_angle" 
                label="Angle" 
                field="rot_angle" 
                :errors="null" 
                desc="Position Angle of the slit in degrees east of north."
                @input="update"
              />
            </div>
            
            <!-- TODO: Validate to make sure this is a floating point number -->
            
            <customfield 
              v-if="datatype == 'IMAGE' && !simple_interface" 
              v-model="defocus" 
              label="Defocus" 
              field="defocus" 
              :errors="null" 
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
import customalert from './util/customalert.vue';

export default {
  props: [
    'errors',
    'index',
    'simple_interface',
    'available_instruments',
    'selectedinstrument',
    'datatype',
    'configurationType',
    'instrumentconfig',
    'show',
    'duration_data'
  ],
  components: {
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
      defocus: 0,
      rot_angle: 0,
      opticalElementUpdates: 0
    }
  },
  computed: {
    readoutModeOptions: function() {
      if (this.selectedinstrument in this.available_instruments) {
        let readoutModes = [];
        for (let rm in this.available_instruments[this.selectedinstrument].modes.readout.modes) {
          readoutModes.push({
              text: this.available_instruments[this.selectedinstrument].modes.readout.modes[rm].name,
              value: this.available_instruments[this.selectedinstrument].modes.readout.modes[rm].code,
              binning: this.available_instruments[this.selectedinstrument].modes.readout.modes[rm].params.binning
          });
        }
        return readoutModes;
      } else {
        return [];
      }
    },
    availableOpticalElementGroups: function() {
      if (this.simple_interface) {
        return {
          filters: {
            type: 'filter',
            label: 'Filter',
            options: [
              {value: 'b', text: 'Blue'},
              {value: 'v', text: 'Green'},
              {value: 'rp', text: 'Red'}
            ]
          }
        }
      } else if (this.selectedinstrument in this.available_instruments) {
        let oe_groups = {};
        for (let oe_group_type in this.available_instruments[this.selectedinstrument].optical_elements) {
          // Each optical element group type has an 's' on the end, but the optical element that is 
          // submitted in the optical_elements should have a key that is the same as a group, without the 's'
          let oe_type = oe_group_type.substring(0, oe_group_type.length - 1);
          oe_groups[oe_type] = {};
          oe_groups[oe_type]['type'] = oe_type;
          oe_groups[oe_type]['label'] = _.capitalize(oe_type);
          let elements = [];
          for (let element in this.available_instruments[this.selectedinstrument].optical_elements[oe_group_type]) {
            if (this.available_instruments[this.selectedinstrument].optical_elements[oe_group_type][element].schedulable) {
              elements.push({
                value: this.available_instruments[this.selectedinstrument].optical_elements[oe_group_type][element].code,
                text: this.available_instruments[this.selectedinstrument].optical_elements[oe_group_type][element].name
              });
            }
          }
          oe_groups[oe_type]['options'] = _.sortBy(elements, 'text');
        }
        return oe_groups; 
      } else {
        return [];
      }
    },
    suggestedLampFlatSlitExposureTime: function() {
      // Update on optical element updates
      this.opticalElementUpdates;
      let slitWidth = this.instrumentconfig.optical_elements.slit;
      if (this.configurationType === 'LAMP_FLAT' && slitWidth) {
        return slitWidthToExposureTime(slitWidth);
      } else {
        return undefined;
      }
    },
    showSlitPosition: function() {
      if (this.selectedinstrument.includes('FLOYDS')) {
        return true;
      } else {
        return false;
      }
    }
  },
  methods: {
    update: function() {
      this.$emit('instrumentconfigupdate');
    },
    updateOpticalElement: function() {
      // The optical element fields are not reactive as they change/ are deleted/ don't exist on start.
      // Increment this reactive variable to watch for changed to the optical elements
      this.opticalElementUpdates += 1;
      this.update();
    },
    instrumentConfigurationfillWindow: function() {
      this.$emit('instrumentconfigurationfillwindow', this.index);
    }
  },
  watch: {
    'instrumentconfig.mode': function(value) {
      for (let mode in this.readoutModeOptions) {
        if (value === this.readoutModeOptions[mode].value) {
          this.instrumentconfig.bin_x = this.readoutModeOptions[mode].binning;
          this.instrumentconfig.bin_y = this.readoutModeOptions[mode].binning;
          this.update();
          return;
        }
      }
    },
    readoutModeOptions: function() {
      this.instrumentconfig.mode = this.available_instruments[this.selectedinstrument].modes.readout.default;
      this.update();
    },
    availableOpticalElementGroups: function(value) {
      // TODO: Implement optical element history
      this.instrumentconfig.optical_elements = {};
      if (this.simple_interface) {
        this.instrumentconfig.optical_elements.filter = 'b';
      } else {
        for (let oe_type in value) {
          if (value[oe_type]['options'].length > 0) {
            this.instrumentconfig.optical_elements[oe_type] = value[oe_type]['options'][0].value;
          }
        }
      }
      this.updateOpticalElement();
    },
    showSlitPosition: function(value) {
      if (value) {
        if (this.instrumentconfig.rot_mode === '') {
          this.instrumentconfig.rot_mode = 'VFLOAT';
        }
      } else {
        this.instrumentconfig.rot_mode = '';
      }
      this.update();
    },
    'instrumentconfig.rot_mode': function(value) {
      if (value === 'SKY') {
        this.instrumentconfig.extra_params.rot_angle = this.rot_angle;        
      } else {
        this.instrumentconfig.extra_params.rot_angle = undefined;
      }
      this.update();
    },
    rot_angle: function(value) {
      this.instrumentconfig.extra_params.rot_angle = value || undefined;
      this.update();
    },
    defocus: function(value) {
      this.instrumentconfig.extra_params.defocus = value || undefined;
      this.update();
    },
    datatype: function(value) {
      if (value === 'IMAGE') {
        this.instrumentconfig.extra_params.defocus = this.defocus;
      } else {
        this.instrumentconfig.extra_params.defocus = undefined;
      }
      this.update();
    }
  }
}
</script>
