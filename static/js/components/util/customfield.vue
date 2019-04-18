<template>
 <span>
    <div class="form-group" :class="{ 'has-error': errors }" v-show="$parent.show">
      <label :for="field" class="col-sm-5 control-label">
        <span class="desc-tooltip" :title="desc">{{ label }}</span>
      </label>
      <div class="col-sm-7">
        <div :class="{ 'input-group': this.$slots['inlineButton'] }">
          <input :id="field" class="form-control" v-bind:value="value" v-on:blur="blur($event.target.value)"
                 v-on:input="update($event.target.value)" :name="field" :type="type || 'text'"/>
          <slot name="inlineButton"></slot>
        </div>
        <span class="help-block text-danger" v-for="error in errors">{{ error }}</span>
      </div>
    </div>
    <span class="collapse-inline" v-show="!$parent.show">
      {{ label }}: <strong>{{ value || '...' }}</strong>
    </span>
  </span>
</template>
<script>
  import moment from 'moment';
  import $ from 'jquery';
  import {datetimeFormat} from '../../utils';
  import tooltip from 'bootstrap';

  export default {
    props: ['value', 'label', 'field', 'errors', 'type', 'desc'],
    mounted: function(){
      var that = this;
      if(this.type === 'datetime'){
        $(this.$el).find('input').datetimepicker({
          format: datetimeFormat,
          minDate: moment().subtract(1, 'days'),
          keyBinds: {left: null, right: null, up: null, down: null}
        }).on('dp.change', function(e){
          that.update(moment(e.date).format(datetimeFormat));
        });
      }
      $(this.$el).find('label > span').tooltip({
        html: true,
        trigger: 'hover click',
        placement: 'top',
        delay: { "show": 200, "hide": 100 }
      });
    },
    methods: {
      update: function(value){
        this.$emit('input', value);
      },
      blur: function(value){
        this.$emit('blur', value);
      }
    },
  };
</script>
