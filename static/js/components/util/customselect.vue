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
      <b-form-select 
        :id="field + '-select-' + $parent.id" 
        :value="value | toLowerCase(lowerOptions)"
        :state="validationState"
        :options="selectOptions"
        @input="update($event)"
      />
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
      {{ label }}: <strong>{{ value || '...' }}</strong>
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
      'options', 
      'errors', 
      'desc',
      'lowerOptions'
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
      },
      selectOptions: function() {
        if (this.lowerOptions) {
          return _.mapValues(this.options, function(opt) {
            if (_.isString(opt.value)) {
              return {value: _.toLower(opt.value), text: opt.text};
            } else {
              return {value: opt.value, text: opt.text};
            }
          });
        } else {
          return this.options;
        }
      }
    },
    filters: {
      toLowerCase: function(value, lowerOptions) {
        if (lowerOptions && _.isString(value)) {
          return _.toLower(value);
        }
        return value;
      }
    },
    methods: {
      update: function(value) {
        this.$emit('input', value);
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
