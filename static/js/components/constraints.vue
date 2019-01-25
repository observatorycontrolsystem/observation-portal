<template>
  <panel :id="'constraints' + $parent.$parent.index" :errors="errors" v-on:show="show = $event"
         :canremove="false" :cancopy="false" icon="fa-lock" title="Constraints" :show="show">
    <div class="alert alert-danger" v-show="errors.non_field_errors" role="alert">
      <span v-for="error in errors.non_field_errors">{{ error }}</span>
    </div>
    <div class="row">
      <div class="col-md-6 compose-help" v-show="show">
        <ul>
          <li>
            Advice on
            <a href="https://lco.global/documentation/airmass-limit" target="_blank" >
              setting the airmass limit.
            </a>
          </li>
        </ul>
      </div>
      <div :class="show ? 'col-md-6' : 'col-md-12'">
        <form class="form-horizontal">
          <customfield v-model="constraints.max_airmass" label="Maximum Airmass" field="max_airmass"
                       v-on:input="update" :errors="errors.max_airmass" desc="Maximum acceptable airmass at which the observation can be scheduled.
                       A plane-parallel atmosphere is assumed.">
          </customfield>
          <customfield v-model="constraints.min_lunar_distance" label="Min. Lunar Separation"
                       field="min_lunar_distance" v-on:input="update" :errors="errors.min_lunar_distance"
                       desc="Minimum acceptable angular separation (degrees) between the target and the moon.">
          </customfield>
        </form>
      </div>
    </div>
  </panel>
</template>
<script>
import {collapseMixin} from '../utils.js';
import panel from './util/panel.vue';
import customfield from './util/customfield.vue';
import customselect from './util/customselect.vue';
export default {
  props: ['constraints', 'errors', 'parentshow'],
  components: {customselect, customfield, panel},
  mixins: [collapseMixin],
  data: function(){
    return {'show': true};
  },
  methods: {
    update: function(){
      this.$emit('constraintsupdate');
    }
  }
};
</script>
