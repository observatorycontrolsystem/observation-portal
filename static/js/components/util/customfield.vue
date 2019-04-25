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
    <b-form-input 
      :id="field" 
      :value="value"
      :state="!hasErrors"
      :type="type || `text`"
      @input="update($event)"
      @blur="blur($event)"
    />
    <slot name="inlineButton"></slot>
    <span class="text-danger" v-for="error in errors" :key="error">{{ error }}</span>
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
