<template>
<span>
  <span class="text-right font-italic extra-help-text">
    <slot name="extra-help-text"/>
  </span>
  <b-form-group
    :id="field + '-fieldgroup-' + $parent.id"
    v-show="$parent.show"
    label-size="sm"
    label-align-sm="right"
    label-cols-sm="4"
    :label-for="field"
  >
    <template 
      slot="label"
    >
      {{ label }}
      <sup 
        v-if="desc"
        class="text-primary" 
        v-b-tooltip=tooltipConfig 
        :title="desc"
      >
        ?
      </sup>
    </template>
    <b-input-group>
      <b-form-input 
        :id="field + '-field-' + $parent.id" 
        :value="value"
        :state="validationState"
        :type="type || `text`"
        @input="update($event)"
        @blur="blur($event)"
      />
      <slot name="inline-input"/>
    </b-input-group>
    <span 
      class="errors text-danger" 
      v-for="error in errors" 
      :key="error"
    >
      {{ error }}
    </span>    
  </b-form-group>
  <span 
    class="mr-4" 
    v-show="!$parent.show"
  > 
    {{ label }}: <strong>{{ displayValue(value) }}</strong>
  </span>
</span>
</template>
<script>
  import _ from 'lodash';
  
  import { tooltipConfig } from '../../utils.js';

  export default {
    props: [
      'value',
      'label', 
      'field', 
      'errors', 
      'type', 
      'desc',
    ],
    data: function() {
      return {
        tooltipConfig: tooltipConfig
      }
    },
    computed: {
      hasErrors: function() {
        return !_.isEmpty(this.errors);
      },
      validationState: function() {
        if (this.errors === null) {
          // No validation displayed
          return null;
        } else if (this.hasErrors) {
          return 'invalid';
        } else {
          return null;
        }
      }
    },
    methods: {
      displayValue: function(value) {
        if (value === 0) {
          return '0';
        } else if (value === '' || value === null) {
          return '...'
        } else {
        return value;
        }
      },
      update: function(value) {
        this.$emit('input', value);
      },
      blur: function(value) {
        this.$emit('blur', value);
      }
    }
  };
</script>
<style scoped>
  .errors {
    font-size: 90%;
  }
  .extra-help-text,
  .extra-help-text div {
    font-size: 90%;
    margin-left: auto !important;
    max-width: 220px;
  }
</style>
