<template>
  <div class="row" :id="id">
    <div class="col-md-12">
      <div class="panel panel-default">
        <div class="panel-heading panel-heading-compact">
          <div class="row">
            <div class="col-4">
              <i class="fa fa-2x fa-fw" :class="icon"></i>
              <i title="Errors in form" class="fa fa-warning fa-2x fa-fw text-danger" v-show="hasError"></i>
              <i title="Section is complete" class="fa fa-check fa-2x fa-fw text-success" v-show="!hasError"></i>
            </div>
            <div class="panel-title col-4">
              {{ title }} <span v-if="index > 0">#{{ index + 1}}</span>
            </div>
            <div class="panel-actions col-4">
              <a class="btn btn-xs btn-danger" v-on:click="remove" v-show="canremove" title="remove">
                <i class="fa fa-trash fa-fw"></i>
              </a>
              <a class="btn btn-xs btn-success" v-on:click="copy" v-show="cancopy" title="copy">
                <i class="fa fa-copy fa-fw"></i>
              </a>
              <a class="btn btn-info btn-xs" v-on:click="clickShow" :title="show ? 'Minimize' : 'Maximize'">
                <i class="fa fa-fw" :class="show ? 'fa-window-minimize' : 'fa-window-maximize'"></i>
              </a>
            </div>
          </div>
        </div>
        <div class="panel-body panel-body-compact">
          <slot :show="show"></slot>
        </div>
      </div>
    </div>
  </div>
</template>
<script>
  import _ from 'lodash';
  export default {
    props: ['id', 'errors', 'show', 'canremove', 'cancopy', 'icon', 'title', 'index'],
    methods:{
      remove: function(){
        if(confirm('Are you sure you want to remove this item?')){
          this.$emit('remove');
        }
      },
      copy: function(){
        this.$emit('copy');
      },
      clickShow: function(){
        this.$emit('show', !this.show);
      }
    },
    computed:{
      hasError: function(){
        return !_.isEmpty(this.errors);
      }
    }
  };
</script>
<style>
  .panel-body-compact {
    padding-bottom: 5px;
  }

  .panel-heading-compact {
    padding: 5px 15px;
  }

  .panel-title {
    font-size: 1.2em;
    text-align: center;
    height: 30px;
    padding-top: 5px;
  }

  .panel-actions {
    text-align: right;
  }

  .fa-2x {
    vertical-align: middle;
  }
</style>
