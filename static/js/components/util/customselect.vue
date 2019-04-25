<template>
  <span>
    <b-form-group
      v-show="$parent.show"
      label-size="sm"
      label-align-sm="right"
      label-cols-sm="4"
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
    <span 
      class="mr-4" 
      v-show="!$parent.show"
    > 
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
