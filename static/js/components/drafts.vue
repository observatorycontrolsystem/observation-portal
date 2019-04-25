<template>
  <b-table 
    striped 
    hover 
    :fields="fields" 
    :items="items" 
    :show-empty="tableIsEmpty"
    empty-text="You have no draft observing requests" 
  >
    <template slot="load" slot-scope="data" class="text-center">
      <b-button 
        variant="info" 
        size="sm" 
        @click="loadDraft(data.value)"
      >
        <i class="fa fa-download"></i>
      </b-button>
    </template>
    <template slot="delete" slot-scope="data">
      <b-button 
        variant="danger" 
        size="sm" 
        @click="deleteDraft(data.value)"
      >
        <i class="fa fa-trash"></i>
      </b-button>
    </template>
  </b-table>
</template>
<script>
  import $ from 'jquery';

  import { formatDate } from '../utils.js';

  export default {
    props: [
      'tab'
    ],
    data: function() {
      return {
        'drafts': [],
        'fields': [
          {
            key: 'load',
            class: 'text-center'
          },
          'id',
          'title',
          'author',
          'proposal',
          'modified_time',
          {
            key: 'delete',
            class: 'text-center'
          },

        ]
      };
    },
    computed: {
      items: function() {
        let items = [];
        for (let i in this.drafts) {
          items.push({
            'load': this.drafts[i].id,
            'title': this.drafts[i].title,
            'id': this.drafts[i].id,
            'author': this.drafts[i].author,
            'proposal': this.drafts[i].proposal,
            'modified_time': formatDate(this.drafts[i].modified),
            'delete': this.drafts[i].id
          });
        }
        return items;
      },
      tableIsEmpty: function() {
        return this.items.length < 1;
      }
    },
    methods: {
      fetchDrafts: function() {
        let that = this;
        $.getJSON('/api/drafts/', function(data) {
          that.drafts = data.results;
        });
      },
      loadDraft: function(id) {
        this.$emit('loaddraft', id);
      },
      deleteDraft: function(id) {
        if (confirm('Are you sure you want to delete this draft?')) {
          let that = this;
          $.ajax({
            type: 'DELETE',
            url: '/api/drafts/' + id + '/'
          }).done(function() {
            that.fetchDrafts();
          });
        }
      }
    },
    watch: {
      tab: function(value) {
        if (value === 3) this.fetchDrafts();
      }
    }
  };
</script>
