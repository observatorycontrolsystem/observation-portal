<template>
  <nav class="bs-docs-sidebar">
    <ul id="sidebar" class="nav nav-stacked">
      <li>
        <a href="#general">
          <i v-if="rootError" class="fa fa-fw fa-warning text-danger"></i>
          <i v-else class="fa fa-fw fa-check text-success"></i>
          General Info
          <div class="errorlist text-danger" v-html="rootErrorList"></div>
        </a>
      </li>
      <li v-for="(request, index) in userrequest.requests">
        <a :href="'#request' + index">
          <i v-if="hasError(['requests', index])" class="fa fa-fw fa-warning text-danger"></i>
          <i v-else class="fa fa-fw fa-check text-success"></i>
          Request #{{ index + 1}}
          <div class="errorlist text-danger" v-html="errorList(['requests', index])"></div>
        </a>
        <ul class="nav nav-stacked">
          <li>
            <a :href="'#target' + index">
              <i class="fa fa-fw" :class="hasError(['requests', index, 'target']) ? 'fa-warning text-danger' : 'fa-check text-success'"></i>
              Target
              <div class="errorlist text-danger" v-html="errorList(['requests', index, 'target'])"></div>
            </a>
          </li>
          <li v-for="(molecule, molIndex) in request.molecules">
            <a :href="'#molecule' + index + molIndex">
              <i class="fa fa-fw" :class="hasError(['requests', index, 'molecules', molIndex]) ? 'fa-warning text-danger' : 'fa-check text-success'"></i>
              Configuration #{{ molIndex + 1}}
              <div class="errorlist text-danger" v-html="errorList(['requests', index, 'molecules', molIndex])"></div>
            </a>
          </li>
          <li v-for="(window, winIndex) in request.windows">
            <a :href="'#window' + index + winIndex">
              <i class="fa fa-fw" :class="hasError(['requests', index, 'windows', winIndex]) ? 'fa-warning text-danger' : 'fa-check text-success'"></i>
              Window #{{ winIndex + 1}}
              <div class="errorlist text-danger" v-html="errorList(['requests', index, 'windows', winIndex])"></div>
            </a>
          </li>
          <li>
            <a :href="'#constraints' + index">
              <i class="fa fa-fw" :class="hasError(['requests', index, 'constraints']) ? 'fa-warning text-danger' : 'fa-check text-success'"></i>
              Constraints
              <div class="errorlist text-danger" v-html="errorList(['requests', index, 'constraints'])"></div>
            </a>
          </li>
        </ul>
      </li>
    </ul>
  </nav>
</template>

<script>
  import _ from 'lodash';
  import {formatField} from '../utils.js';

  export default {
    props: ['userrequest', 'errors'],
    computed: {
      rootError: function(){
        return !_.isEmpty(this.errors);
      },
      rootErrorList: function(){
        var errortext = '';
        for(var k in this.errors){
          if(k != 'requests'){
            errortext += (formatField(k) + ': ');
            for(var e in this.errors[k]){
              errortext += (this.errors[k][e] + '<br/>');
            }
          }
        }
        return errortext;
      }
    },
    methods: {
      getErrors: function(path){
        return _.get(this.errors, path, []);
      },
      hasError: function(path){
        return !_.isEmpty(this.getErrors(path));
      },
      errorList: function(path){
        var errortext = '';
        for(var k in this.getErrors(path)){
          if(!['request', 'target', 'molecules', 'windows', 'constraints'].includes(k)){
            errortext += (formatField(k) + ': ');
            for(var e in this.getErrors(path)[k]){
              errortext += (this.getErrors(path)[k][e] + '<br/>');
            }
          }
        }
        return errortext;
      }
    }
  };
</script>
<style>
/* sidebar */
.bs-docs-sidebar {
    margin-top: 20px;
    margin-bottom: 20px;
    position: fixed;
}

/* all links */
.bs-docs-sidebar .nav>li>a {
    color: #999;
    border-left: 2px solid transparent;
    padding: 4px 20px;
    font-size: 16px;
    font-weight: 400;
}

/* nested links */
.bs-docs-sidebar .nav .nav>li>a {
    padding-top: 1px;
    padding-bottom: 1px;
    padding-left: 30px;
    font-size: 14px;
}

/* active & hover links */
.bs-docs-sidebar .nav>.active>a,
.bs-docs-sidebar .nav>li>a:hover,
.bs-docs-sidebar .nav>li>a:focus {
    color: #009ec3;
    text-decoration: none;
    background-color: transparent;
    border-left-color: #31b0d5;
}
/* all active links */
.bs-docs-sidebar .nav>.active>a,
.bs-docs-sidebar .nav>.active:hover>a,
.bs-docs-sidebar .nav>.active:focus>a {
    font-weight: 700;
}
/* nested active links */
.bs-docs-sidebar .nav .nav>.active>a,
.bs-docs-sidebar .nav .nav>.active:hover>a,
.bs-docs-sidebar .nav .nav>.active:focus>a {
    font-weight: 500;
}

/* hide inactive nested list */
.bs-docs-sidebar .nav ul.nav {
    display: none;
}
/* show active nested list */
.bs-docs-sidebar .nav>.active>ul.nav {
    display: block;
}
.errorlist {
  padding-left: 22px;
  font-size: 14px;
  max-width: 300px;
}
</style>
