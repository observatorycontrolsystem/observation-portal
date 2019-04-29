<template>
  <span>
    <b-form-group
      :id="field + '-datetimegroup-' + $parent.id"
      v-show="$parent.show"
      label-size="sm"
      label-align-sm="right"
      label-cols-sm="4"
      :description="desc"
      :label="label"
      :label-for="field"
    >
      <VueCtkDateTimePicker 
        v-model="theValue"
        label=""
        :format="datetimeFormat"
        :formatted="datetimeFormat"
        :id="field + '-datetimefield-' + $parent.id" 
        :error="hasErrors"
        :no-header="true"
        :no-button-now="true"
        :no-button="true"
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
  import VueCtkDateTimePicker from 'vue-ctk-date-time-picker';

  import { datetimeFormat } from '../../utils';
  
  export default {
    props: [
      'value',
      'label', 
      'field', 
      'errors', 
      'type', 
      'desc',
    ],
    components: {
      VueCtkDateTimePicker
    },
    data: function() {
      return {
        datetimeFormat: datetimeFormat,
        theValue: this.value
      }
    },
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
<style scoped>
  @import '~vue-ctk-date-time-picker/dist/vue-ctk-date-time-picker.css';
</style>
<style>
  /* 
   * Override the default ctk datetime picker styles to look like other
   * bootstrap 4 input fields, using scoped style does not work 
   */
  .date-time-picker .field .field-input {
    color: inherit !important;
    font-size: 0.875rem !important;
    padding-top: 0rem !important;
    font-family: inherit !important;
    height: 32px !important;
    min-height: 32px !important;
  }
  .date-time-picker span.errors {
    font-size: 80%;
  }
</style>
