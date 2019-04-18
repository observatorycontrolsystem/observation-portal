<template>
  <span>
    <b-form-group
      v-show="$parent.show"
      label-align-sm="right"
      label-cols-sm="5"
      :description="desc"
      :label="label"
      :label-for="field"
    >
      <b-form-select 
        :id="field" 
        :value="value"
        :state="!hasErrors"
        :options="options"
        @input="update($event)"
      />
      <span class="text-danger" :key="error" v-for="error in errors">{{ error }}</span>
    </b-form-group>
    <!-- TODO: This is what is supposed to be displayed for this field when the parent object is collapsed -->
    <span class="collapse-inline" v-show="!$parent.show">
      {{ label }}: <strong>{{ value || '...' }}</strong>
    </span>
  </span>
</template>
<script>
  import _ from 'lodash';
  import $ from 'jquery';

  export default {
    props: [
      'value',
      'label', 
      'field', 
      'options', 
      'errors', 
      'desc'
    ],
    computed: {
      hasErrors: function() {
        return !_.isEmpty(this.errors);
      }
    },
    methods: {
      update: function(value) {
        this.$emit('input', value);
      }
    }
  };
</script>
