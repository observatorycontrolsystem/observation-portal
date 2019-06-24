<template>
  <div>
    <div id="archive-table-toolbar">
      <b-button
        @click="downloadSelected"
        variant="outline-secondary"
        size="sm"
      >
        <i class="fa fa-check"></i> Download Selected
      </b-button>
      <b-button
        @click="downloadAll"
        variant="outline-secondary"
        size="sm"
      >
        <i class="fa fa-download"></i> Download All
      </b-button>
      <b-link
        :href="archiveLink"
        target="_blank"
        class="btn btn-sm btn-outline-secondary"
      >
        <i class="fa fa-arrow-right"></i> View on Archive
      </b-link>
    </div>
    <table id="archive-table" class="table-sm"></table>
  </div>
</template>
<script>
  import 'bootstrap-table';
  import $ from 'jquery';
  import { formatDate } from '../utils.js';
  import { archiveRoot, archiveUIRoot, downloadAll, downloadZip } from '../archive.js';

  export default{
    props: [
      'requestid'
    ],
    watch: {
      requestid: function(){
        $('#archive-table').bootstrapTable('refresh',
          {url: archiveRoot + 'frames/?limit=1000&REQNUM=' + this.requestid}
        );
      }
    },
    methods: {
      downloadSelected: function() {
        let frameIds = [];
        let selections = $('#archive-table').bootstrapTable('getSelections');
        if (selections.length == 0) {
          alert('Please select at least one frame to download');
          return;
        }
        for(let i = 0; i < selections.length; i++){
          frameIds.push(selections[i].id);
        }
        downloadZip(frameIds);
      },
      downloadAll: function(){
        downloadAll(this.requestid);
      }
    },
    computed: {
      archiveLink: function(){
        return archiveUIRoot + '?REQNUM=' + this.requestid + '&start=2014-01-01';
      }
    },
    mounted: function(){
      let that = this;
      $('#archive-table').bootstrapTable({
        url: null,
        responseHandler: function(res){
          if(res.count > 1000){
            alert('More than 1000 results found, please view on archive to view all data');
          }
          that.$emit('dataLoaded', res.results);
          return res.results;
        },
        onClickRow: function(row){
          that.$emit('rowClicked', row);
        },
        formatNoMatches: function(){
          return 'No data available.';
        },
        queryParamsType: '',
        idField: 'id',
        pagination: true,
        pageSize: 10,
        buttonsClass: 'outline-secondary',
        classes: 'table table-hover',
        sortName: 'filename',
        sortOrder: 'asc',
        maintainSelected: true,
        checkboxHeader: true,
        toolbar: '#archive-table-toolbar',
        columns: [{
          field: 'state',
          title: '',
          checkbox: true,
        },{
          field: 'filename',
          title: 'filename',
          sortable: 'true',
        },{
          field: 'DATE_OBS',
          title: 'DATE_OBS',
          sortable: 'true',
          formatter: function(value){
            return formatDate(value);
          }
        },{
          field: 'FILTER',
          title: 'filter',
          sortable: 'true',
        },{
          field: 'OBSTYPE',
          title: 'obstype',
          sortable: 'true',
        },{
          field: 'RLEVEL',
          title: 'Reduction',
          sortable: 'true',
          formatter: function(value){
            switch(value){
              case 0:
                return 'raw';
              case 11:
                return 'quicklook';
              case 91:
                return 'reduced';
            }
          }
        }]
      });
    }
  };
</script>
<style>
  #archive-table > tbody > tr {
    cursor: pointer;
  }
</style>
