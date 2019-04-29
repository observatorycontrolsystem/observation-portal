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
    :description="desc"
    :label="label"
    :label-for="field"
  >
    <b-input-group size="sm">
      <b-form-input 
        size="sm"
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
  
  export default {
    props: [
      'value',
      'label', 
      'field', 
      'errors', 
      'type', 
      'desc',
    ],
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
          return 'valid';
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
    font-size: 80%;
  }
  .extra-help-text {
    font-size: 80%;
  }
</style>
