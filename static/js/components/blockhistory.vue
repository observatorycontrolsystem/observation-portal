<template>
  <div>
    <div class="blockHistoryPlot" id="plot">
      <plot_controls v-show="showZoomControls" v-on:plotZoom="plotZoom"></plot_controls>
    </div>
    <div class="blockHistoryPlotLegend text-center">
      <ul class="list-inline">
        <li class="CANCELED legend-item"></li>
        <li>Superseded by new schedule</li>
        <li class="NOT_ATTEMPTED legend-item"></li>
        <li>Not Attempted</li>
        <li class="SCHEDULED legend-item"></li>
        <li>Scheduled</li>
        <li class="IN_PROGRESS legend-item"></li>
        <li>In Progress</li>
        <li class="FAILED legend-item"></li>
        <li>Failed</li>
        <li class="ABORTED legend-item"></li>
        <li>Aborted</li>
        <li class="PARTIALLY-COMPLETED legend-item"></li>
        <li>Partially Completed</li>
        <li class="COMPLETED legend-item"></li>
        <li>Completed</li>
      </ul>
    </div>
  </div>
</template>
<script>
import vis from 'vis';
import $ from 'jquery';
import _ from 'lodash';
import 'vue-style-loader!vis/dist/vis.css';
import 'vue-style-loader!../../css/plot_style.css';
import plot_controls from './util/plot_controls.vue';
import {plotZoomMixin} from './util/plot_mixins.js';

export default {
  props: ['data', 'showZoomControls'],
  mixins: [plotZoomMixin],
  components: {plot_controls},
  data: function () {

    var options = {
      groupOrder: 'content',
      maxHeight: '450px',
      minHeight: '120px',
      align: 'right',
      dataAttributes: ['toggle', 'html'],
      selectable: false,
      snap: null,
      zoomKey: 'ctrlKey',
      moment: function (date) {
        return vis.moment(date).utc();
      },
      tooltip: {
        overflowMethod: 'cap',
      }
    };

    return {
      options: options
    };
  },
  computed: {
    toVis: function () {
      var visGroups = new vis.DataSet();
      var visData = new vis.DataSet();

      var timeline_min = 0;
      var timeline_max = 0;
      if(this.data.length > 0) {

        var previousBlock = this.data[0];
        var previousBlockIndex = 1;
        var index = 0;

        for (var i = 0; i < this.data.length; i++) {
          var block = this.data[i];
          block.start += 'Z';
          block.end += 'Z';
          if (block.failed) {
            block.fail_reason = '<br/>reason: ' + block.fail_reason;
          }

          if (block.percent_completed > 0) {
            block.percent_completed = '<br/>percent completed: ' + block.percent_completed.toFixed(1);
          }
          else {
            block.percent_completed = '';
          }

          if (block.cancel_date != null) {
            block.cancel_date = '<br/>canceled: ' + block.cancel_date.replace('T', ' ');
          }
          else {
            block.cancel_date = '';
          }
          if (block.start != previousBlock.start || block.site != previousBlock.site || block.status != previousBlock.status
            || block.observatory != previousBlock.observatory || block.telescope != previousBlock.telescope) {

            var className = 'timeline_block ' + previousBlock.status;

            visGroups.add({id: index, content: previousBlockIndex});

            visData.add({
              id: index,
              group: index,
              title: 'telescope: ' + previousBlock.site + '.' + previousBlock.observatory + '.' + previousBlock.telescope + previousBlock.percent_completed + previousBlock.fail_reason + previousBlock.cancel_date + '<br/>start: ' + previousBlock.start.replace('T', ' ') + '<br/>end: ' + previousBlock.end.replace('T', ' '),
              className: className,
              start: previousBlock.start,
              end: previousBlock.end,
              toggle: 'tooltip',
              html: true,
              type: 'range'
            });
            index++;
            previousBlockIndex = i + 1;
          }
          previousBlock = block;
        }

        visGroups.add({id: index, content: previousBlockIndex});

        visData.add({
          id: index,
          group: index,
          title: 'telescope: ' + previousBlock.site + '.' + previousBlock.observatory + '.' + previousBlock.telescope + previousBlock.percent_completed + previousBlock.fail_reason + previousBlock.cancel_date + '<br/>start: ' + previousBlock.start.replace('T', ' ') + '<br/>end: ' + previousBlock.end.replace('T', ' '),
          className: 'timeline_block ' + previousBlock.status,
          start: previousBlock.start,
          end: previousBlock.end,
          toggle: 'tooltip',
          html: true,
          type: 'range'
        });
        index++;

        timeline_min = new Date(visData.get(index - 1)['start']);
        timeline_max = new Date(visData.get(index - 1)['end']);
        if (index > 12) {
          for (var k = index - 1; k >= index - 12; k--) {
            var start = new Date(visData.get(k)['start']);
            var end = new Date(visData.get(k)['end']);
            if (start < timeline_min) {
              timeline_min = start;
            }
            if (end > timeline_max) {
              timeline_max = end;
            }
          }
          timeline_max.setMinutes(timeline_max.getMinutes() + 30);
          timeline_min.setMinutes(timeline_min.getMinutes() - 30);
        }
      }

      return {datasets: visData, groups: visGroups, window: {start: timeline_min, end: timeline_max}};
    }
  },
  watch: {
    data: function () {
      var datasets = this.toVis;
      //Need to first zero out the items and groups or vis.js throws an error
      this.plot.setItems(new vis.DataSet());
      this.plot.setGroups(new vis.DataSet());
      this.plot.setGroups(datasets.groups);
      this.plot.setItems(datasets.datasets);
      this.plot.setWindow(datasets.window.start, datasets.window.end);
    }
  },
  mounted: function () {
    this.plot = this.buildPlot();
  },
  methods: {
    buildPlot: function () {
      // Set a unique name for the plot element, since vis.js needs this to separate plots
      this.$el.setAttribute('class', _.uniqueId(this.$el.className));
      var plot = new vis.Timeline(document.getElementById('plot'), new vis.DataSet([]), this.options);
      var that = this;
      plot.on('changed', function () {
        //HAX
        $(that.$el).find('.vis-group').mouseover(function () {
          $(that.$el).find('.vis-item').tooltip({container: 'body', 'placement': 'top'});
        });
      });
      return plot;
    }
  }
};
</script>
