<template>
  <b-container v-show="resultCount > 0">
    <h3>
      <i class="fas fa-info fa-2x fa-border fa-pull-left"></i>
      <a 
        :href="guiLink" 
        target="_blank"
      >
        {{ resultCount }}
      </a>
      existing frames that you have access to have been found on the LCO science archive covering this RA/Dec.
    </h3>
  </b-container>
</template>
<script>
  import $ from 'jquery';
  import _ from 'lodash';

  import { archiveRoot, archiveUIRoot } from '../archive.js';

  export default {
    props: [
      'ra', 
      'dec'
    ],
    data: function() {
      return {resultCount: 0};
    },
    created: function() {
      this.setResultCount();
    },
    computed: {
      guiLink: function() {
        return archiveUIRoot + '?OBSTYPE=EXPOSE&OBSTYPE=REPEAT_EXPOSE&start=2014-05-01&covers=POINT(' + this.ra + ' ' + this.dec +')';
      }
    },
    methods:{
      setResultCount: _.debounce(function() {
        let that = this;
        $.getJSON(archiveRoot + 'frames/?OBSTYPE=EXPOSE&OBSTYPE=REPEAT_EXPOSE&covers=POINT(' + that.ra + ' ' + that.dec +')', function(data) {
          that.resultCount = data.count;
        });
      }, 500)
    },
    watch: {
      ra: function(val) {
        if (val && this.dec){
          this.setResultCount();
        }
      },
      dec: function(val) {
        if (val && this.ra){
          this.setResultCount();
        }
      }
    }
  };
</script>
