<template>
  <panel :show="show"
    :id="'constraints' + $parent.$parent.index" 
    :errors="errors" 
    :canremove="false" 
    :cancopy="false" 
    icon="fa-lock" 
    title="Constraints" 
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
              Advice on
              <a href="https://lco.global/documentation/airmass-limit" target="_blank" >
                setting the airmass limit.
              </a>
            </li>
          </ul>
        </b-col>
        <b-col :md="show ? 6 : 12">
          <b-form>
            <customfield 
              v-model="constraints.max_airmass" 
              label="Maximum Airmass" 
              field="max_airmass"
              :errors="errors.max_airmass" 
              desc="Maximum acceptable airmass at which the observation can be scheduled. A plane-parallel atmosphere is assumed."
              @input="update" 
            />
            <customfield 
              v-model="constraints.min_lunar_distance" 
              label="Minimum Lunar Separation"
              field="min_lunar_distance" 
              :errors="errors.min_lunar_distance"
              desc="Minimum acceptable angular separation (degrees) between the target and the moon."
              @input="update" 
            />
          </b-form>
        </b-col>
      </b-row>
    </b-container>
  </panel>
</template>
<script>
  import { collapseMixin } from '../utils.js';
  import panel from './util/panel.vue';
  import alert from './util/alert.vue';
  import customfield from './util/customfield.vue';

  export default {
    props: [
      'constraints', 
      'errors', 
      'parentshow'
    ],
    components: {
      customfield, 
      panel,
      alert
    },
    mixins: [
      collapseMixin
    ],
    data: function() {
      return {'show': true};
    },
    methods: {
      update: function(){
        this.$emit('constraintsupdate');
      }
    }
  };
</script>
